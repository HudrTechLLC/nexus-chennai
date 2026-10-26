-- 0007_02 · Evidence and audio statement files (spec G4, D3.4; nexus-5, chief's decision 26 Oct).
--
-- Private bucket `evidence`. Objects are stored as uploaded (original bytes, no metadata stripping)
-- so the sha256 recorded in evidence_media / custody stays verifiable. Keys are
-- <crime_id>/<uuid>.<ext>; the policies take the crime id from the key and reuse the case rules
-- from 0002: can_write_crime to upload, can_read_crime to read. No UPDATE or DELETE policy, so an
-- uploaded file can never be replaced or removed through the API (custody). anon has no access.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('evidence', 'evidence', false, 4194304,
        array['image/jpeg', 'image/png', 'image/webp', 'application/pdf', 'video/mp4',
              'audio/mpeg', 'audio/mp4', 'audio/ogg', 'audio/webm', 'audio/wav'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "police upload evidence for writable cases" on storage.objects;
create policy "police upload evidence for writable cases" on storage.objects for insert to authenticated
  with check (
    bucket_id = 'evidence'
    and name ~ '^[A-Z]+-[A-Z0-9]+-\d{4}-\d+/[0-9a-f-]{36}\.(jpg|png|webp|pdf|mp4|mp3|m4a|ogg|webm|wav)$'
    and public.can_write_crime(split_part(name, '/', 1))
  );

drop policy if exists "police read evidence for readable cases" on storage.objects;
create policy "police read evidence for readable cases" on storage.objects for select to authenticated
  using (bucket_id = 'evidence' and public.can_read_crime(split_part(name, '/', 1)));

-- Audio statements: officers may add them like text statements (0002 "add statements").
-- Evidence rows: 0002 already grants insert with can_write_crime ("add evidence").

-- Rollback:
--   drop policy if exists "police upload evidence for writable cases" on storage.objects;
--   drop policy if exists "police read evidence for readable cases" on storage.objects;
--   delete from storage.buckets where id = 'evidence';  -- only when empty
