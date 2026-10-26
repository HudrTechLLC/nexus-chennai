-- 0007_06 · Evidence rows are recorded by the database, tied to the caller's own upload
-- (spec CAP-02, D3.4; chief's decision after the D-029 limit; nexus-5).
--
-- Before: police roles had INSERT on evidence_media and statements, so a row could carry any
-- sha256, custody or uploaded_by. Now:
--   * record_evidence(p jsonb) (security definer) is the only way to add an evidence row or an
--     audio statement. It requires an object in the private `evidence` bucket at that path whose
--     OWNER is the caller (storage sets owner_id from the uploader's session), takes the size and
--     media type from storage, not from the client, and refuses a path that is already recorded.
--     uploaded_by, the custody step and the witness reference are set here.
--   * Direct INSERT on evidence_media and statements is revoked from authenticated. FIR statements
--     still come from file_fir (definer) and are unaffected.
--   * case_diary.author is set from the signed-in officer's profile by a trigger, so the client
--     cannot write someone else's name. Service-role and seed inserts (no auth.uid()) keep theirs.
-- The sha256 itself is still computed by the upload route over the original bytes (the database
-- never sees the bytes); evidence-check.mjs verifies stored object = recorded hash.

create or replace function public.record_evidence(p jsonb) returns text
language plpgsql security definer set search_path = public as $$
declare
  v_uid    uuid := auth.uid();
  v_crime  text := p->>'crime_id';
  v_path   text := p->>'path';
  v_sha    text := lower(coalesce(p->>'sha256', ''));
  v_target text := coalesce(p->>'target', 'evidence');
  v_kind   text := p->>'kind';
  v_meta   jsonb;
  v_bytes  bigint;
  v_mime   text;
  v_id     text;
  v_n      integer;
  v_now    timestamptz := now();
begin
  if v_uid is null then raise exception 'sign in first' using errcode = '42501'; end if;
  if v_crime is null or not exists (select 1 from crimes where crime_id = v_crime) then
    raise exception 'unknown case' using errcode = '22023';
  end if;
  if not public.can_write_crime(v_crime) then
    raise exception 'you can add evidence only to cases your station may write' using errcode = '42501';
  end if;
  if v_path is null or v_path !~ ('^' || v_crime || '/[0-9a-f-]{36}\.(jpg|png|webp|pdf|mp4|mp3|m4a|ogg|webm|wav)$') then
    raise exception 'path must be <crime_id>/<uuid>.<ext> for this case' using errcode = '22023';
  end if;
  if v_sha !~ '^[0-9a-f]{64}$' then raise exception 'sha256 must be 64 hex characters' using errcode = '22023'; end if;
  if v_target not in ('evidence', 'statement') then raise exception 'target must be evidence or statement' using errcode = '22023'; end if;

  -- The object must exist and must have been uploaded by this caller.
  select o.metadata into v_meta from storage.objects o
   where o.bucket_id = 'evidence' and o.name = v_path and o.owner_id = v_uid::text;
  if v_meta is null then
    raise exception 'no file you uploaded is stored at that path' using errcode = '42501';
  end if;
  v_bytes := nullif(v_meta->>'size', '')::bigint;
  v_mime := v_meta->>'mimetype';
  if p ? 'bytes' and (p->>'bytes')::bigint is distinct from v_bytes then
    raise exception 'recorded size does not match the stored file' using errcode = '22023';
  end if;
  if exists (select 1 from evidence_media where storage_path = v_path)
     or exists (select 1 from statements where audio_path = v_path) then
    raise exception 'this file is already recorded' using errcode = '23505';
  end if;

  if v_target = 'statement' then
    if v_mime is null or v_mime not like 'audio/%' then raise exception 'an audio statement needs an audio file' using errcode = '22023'; end if;
    select count(*) + 1 into v_n from statements where crime_id = v_crime;
    v_id := 'ST-' || v_crime || '-A' || left(split_part(split_part(v_path, '/', 2), '.', 1), 8);
    insert into statements (statement_id, crime_id, witness_ref, mode, audio_path, recorded_at, synthetic)
    values (v_id, v_crime, 'W-' || v_n || ' (masked)', 'audio', v_path, v_now, true);
  else
    if v_kind is null or v_kind not in ('cctv_still', 'cctv_clip', 'photo', 'scan', 'audio', 'document') then
      raise exception 'unknown evidence kind' using errcode = '22023';
    end if;
    if (v_kind in ('cctv_still', 'photo') and v_mime not like 'image/%')
       or (v_kind = 'cctv_clip' and v_mime <> 'video/mp4')
       or (v_kind = 'audio' and v_mime not like 'audio/%')
       or (v_kind = 'document' and v_mime <> 'application/pdf')
       or (v_kind = 'scan' and v_mime not like 'image/%' and v_mime <> 'application/pdf') then
      raise exception 'a % file cannot be filed as %', v_mime, v_kind using errcode = '22023';
    end if;
    v_id := 'EV-' || split_part(split_part(v_path, '/', 2), '.', 1);
    insert into evidence_media (evidence_id, crime_id, kind, storage_path, sha256, captured_at, camera_id,
                                uploaded_by, custody, synthetic)
    values (v_id, v_crime, v_kind, v_path, v_sha, nullif(p->>'captured_at', '')::timestamptz,
            nullif(left(trim(coalesce(p->>'camera_id', '')), 40), ''), v_uid::text,
            jsonb_build_array(jsonb_build_object('at', v_now, 'by', v_uid, 'action', 'uploaded',
                                                 'sha256', v_sha, 'bytes', v_bytes, 'mime', v_mime)),
            true);
  end if;

  insert into audit_log (who, what, object_type, object_id, details)
  values (v_uid, case when v_target = 'statement' then 'add_audio_statement' else 'add_evidence' end, 'crime', v_crime,
          jsonb_build_object('id', v_id, 'path', v_path, 'sha256', v_sha, 'bytes', v_bytes));
  return v_id;
end
$$;
revoke all on function public.record_evidence(jsonb) from public, anon;
grant execute on function public.record_evidence(jsonb) to authenticated;

-- Direct writes are closed; the RPC above (and file_fir for typed FIR statements) are the paths in.
revoke insert on public.evidence_media, public.statements from authenticated;

-- case_diary.author comes from the signed-in officer, never from the client.
create or replace function public.case_diary_author() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is not null then
    new.author := coalesce((select name from profiles where user_id = auth.uid()), auth.uid()::text);
  end if;
  return new;
end
$$;
revoke all on function public.case_diary_author() from public, anon, authenticated;
drop trigger if exists trg_case_diary_author on public.case_diary;
create trigger trg_case_diary_author before insert on public.case_diary
  for each row execute function public.case_diary_author();

-- Rollback:
--   drop trigger if exists trg_case_diary_author on public.case_diary;
--   drop function if exists public.case_diary_author();
--   grant insert on public.evidence_media, public.statements to authenticated;
--   drop function if exists public.record_evidence(jsonb);
