-- 0007_07 · Per-alert scoring-weights version + captured_from back in the evidence audit (nexus-5).
--
-- 1. link_alerts.weights_version (text, nullable): the scoring weights version an alert was scored
--    with (combine.py WEIGHTS_VERSION, e.g. 'f2-default-v1', or 'custom'). nexus-3's writer fills it;
--    rows written before that stay NULL and /console/admin shows them as "pre-versioning".
--    No default on purpose: a default would claim a version for alerts nobody recorded.
-- 2. record_evidence: accepts p.captured_from ('officer' | 'exif') and puts it in the audit_log
--    details again (the pre-0007_06 route recorded it). Same signature, grants and checks otherwise.

alter table public.link_alerts add column if not exists weights_version text;
comment on column public.link_alerts.weights_version is 'Scoring weights version used (combine.py WEIGHTS_VERSION); NULL = scored before versioning was recorded.';

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
  v_from   text := nullif(p->>'captured_from', '');
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
  if v_from is not null and v_from not in ('officer', 'exif') then raise exception 'captured_from must be officer or exif' using errcode = '22023'; end if;

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
          jsonb_strip_nulls(jsonb_build_object('id', v_id, 'path', v_path, 'sha256', v_sha, 'bytes', v_bytes,
                                            'captured_from', v_from)));
  return v_id;
end
$$;
revoke all on function public.record_evidence(jsonb) from public, anon;
grant execute on function public.record_evidence(jsonb) to authenticated;

-- Rollback:
--   alter table public.link_alerts drop column if exists weights_version;
--   re-run the record_evidence definition from 0007_06_record_evidence.sql
