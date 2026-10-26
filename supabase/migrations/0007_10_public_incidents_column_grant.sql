-- 0007_10 · Officers may change only the appeal fields the console edits (nexus-5).
-- Found in review on 26 Oct: `authenticated` had table-wide UPDATE and INSERT on public_incidents. The
-- publish guard (0006_02, 0007_08, 0007_09) checks title, area_label, summary and looking_for, but an officer
-- could still set cell, time_window, category or week straight through the API, and those are published as-is.
-- `cell` is H3 r8 only by convention: an r15 cell would publish an exact point.
--
-- Now:
--   * UPDATE is limited to the columns the console writes: title, area_label, summary, looking_for, status
--     (saveAppeal) and images (nexus-6's stills, 0004_06_05). approved_by and published_at are still set by
--     the guard trigger, which column privileges do not restrict. RLS (can_write_crime) is unchanged.
--   * INSERT is revoked. Drafts are written by the worker with the service role; nothing in the console
--     inserts appeals as an officer.
-- The service role keeps full access.

revoke insert, update on public.public_incidents from authenticated;
grant update (title, area_label, summary, looking_for, status, images) on public.public_incidents to authenticated;
drop policy if exists "officers draft public_incidents" on public.public_incidents;

-- Rollback:
--   revoke update (title, area_label, summary, looking_for, status, images) on public.public_incidents from authenticated;
--   grant insert, update on public.public_incidents to authenticated;
--   create policy "officers draft public_incidents" on public.public_incidents for insert to authenticated
--     with check (crime_id is not null and public.can_write_crime(crime_id));
