-- 0004_06_05 · Blurred stills on public appeals (spec PUB-02, J1; WS4-09). Owner: nexus-6 (web).
--
-- Flow: the officer picks a case still on the appeal editor → the Next server action downloads the
-- original from the PRIVATE `evidence` bucket under the officer's session, blurs the whole image
-- (whole_image_downscale_v1, no face/plate detection) and re-encodes it without metadata → uploads the
-- copy to the PUBLIC `appeal-public` bucket at <public_incident_id>/<uuid>.jpg → appends an entry to
-- public_incidents.images. Originals never leave `evidence`.
--
-- Guards here:
--   * the bucket takes small JPEGs only; keys use the appeal id, never a crime id;
--   * only officers who can write the appeal's case may add or remove objects (no update);
--   * a trigger on public_incidents.images checks every entry points at an existing appeal-public
--     object under THIS appeal's prefix, is marked blurred, and names evidence of THIS appeal's case.
-- Known limit (README Limitations, chief's decision): an officer with write access could still upload
-- an unblurred JPEG straight to the bucket through the storage API; the app path always blurs.
-- NOTE: adds a trigger to public_incidents (0002, nexus-1's table), agreed via nexus-chief.

-- ---------- bucket ----------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('appeal-public', 'appeal-public', true, 307200, array['image/jpeg'])
on conflict (id) do update set public = true, file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- True when the caller may write the case behind this appeal.
create or replace function public.appeal_can_write(p_public_incident_id text) returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce((select public.can_write_crime(p.crime_id) from public.public_incidents p
                   where p.public_incident_id = p_public_incident_id and p.crime_id is not null), false)
$$;
revoke all on function public.appeal_can_write(text) from public, anon;
grant execute on function public.appeal_can_write(text) to authenticated;

drop policy if exists "officers add appeal stills" on storage.objects;
create policy "officers add appeal stills" on storage.objects for insert to authenticated
  with check (
    bucket_id = 'appeal-public'
    and name ~ '^[A-Za-z0-9._-]{3,64}/[0-9a-f-]{36}\.jpg$'
    and public.appeal_can_write(split_part(name, '/', 1))
  );
-- remove() reads the object first, so police need select on this (public) bucket's rows.
drop policy if exists "police list appeal stills" on storage.objects;
create policy "police list appeal stills" on storage.objects for select to authenticated
  using (bucket_id = 'appeal-public' and public.current_role_name() is not null);
drop policy if exists "officers remove appeal stills" on storage.objects;
create policy "officers remove appeal stills" on storage.objects for delete to authenticated
  using (bucket_id = 'appeal-public' and public.appeal_can_write(split_part(name, '/', 1)));

-- ---------- images integrity ----------
create or replace function public.public_incidents_images_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_item jsonb;
  v_path text;
begin
  if tg_op = 'UPDATE' and new.images is not distinct from old.images then
    return new;
  end if;
  if jsonb_typeof(new.images) <> 'array' then
    raise exception 'images must be a list' using errcode = 'check_violation';
  end if;
  if jsonb_array_length(new.images) > 8 then
    raise exception 'an appeal can show at most 8 stills' using errcode = 'check_violation';
  end if;
  for v_item in select * from jsonb_array_elements(new.images) loop
    v_path := v_item ->> 'path';
    if v_path is null or split_part(v_path, '/', 1) <> new.public_incident_id
       or split_part(v_path, '/', 2) !~ '^[0-9a-f-]{36}\.jpg$' or split_part(v_path, '/', 3) <> '' then
      raise exception 'still % is not stored under this appeal', coalesce(v_path, '(no path)') using errcode = 'check_violation';
    end if;
    if coalesce((v_item ->> 'blurred')::boolean, false) is not true then
      raise exception 'still % is not marked blurred', v_path using errcode = 'check_violation';
    end if;
    if not exists (select 1 from storage.objects o where o.bucket_id = 'appeal-public' and o.name = v_path) then
      raise exception 'still % has no blurred copy in appeal-public', v_path using errcode = 'check_violation';
    end if;
    if v_item ->> 'evidence_id' is null or not exists (
         select 1 from public.evidence_media e where e.evidence_id = v_item ->> 'evidence_id' and e.crime_id = new.crime_id) then
      raise exception 'still % does not come from this case''s evidence', v_path using errcode = 'check_violation';
    end if;
  end loop;
  return new;
end $$;
revoke all on function public.public_incidents_images_guard() from public, anon;

drop trigger if exists trg_public_incidents_images_guard on public.public_incidents;
create trigger trg_public_incidents_images_guard before insert or update of images on public.public_incidents
  for each row execute function public.public_incidents_images_guard();

-- Rollback:
--   drop trigger if exists trg_public_incidents_images_guard on public.public_incidents;
--   drop function if exists public.public_incidents_images_guard();
--   drop policy if exists "officers add appeal stills" on storage.objects;
--   drop policy if exists "police list appeal stills" on storage.objects;
--   drop policy if exists "officers remove appeal stills" on storage.objects;
--   drop function if exists public.appeal_can_write(text);
--   delete from storage.buckets where id = 'appeal-public';  -- only when empty
