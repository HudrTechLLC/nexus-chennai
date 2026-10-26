-- 0007_17 · Onboarding: one "Lat/Long" column satisfies both lat and lon (WS1-23; nexus-1, chief's ask 27 Oct).
--
-- A station export often keeps both coordinates in one column ("13.19, 80.18"). The worker maps that column to `lat`
-- with the transform `latlong_lat`, and the registered view derives `lon` from the same column (latlong_lon). The
-- mapping table keys on (run_id, source_col), so there cannot be a second row for `lon`. 0007_15's approve check
-- therefore refused such a mapping ("required fields not mapped: lon"). This replaces onboarding_decide only:
--   * lon counts as mapped when a row maps lat with latlong_lat (the console applies the same rule);
--   * lon mapped by its own column as well as by a latlong_lat column is "mapped more than once".
-- Same signature, grants and admin check as 0007_15.

create or replace function public.onboarding_decide(p_run_id uuid, p_decision text, p_reason text default null)
returns text
language plpgsql volatile security definer set search_path = public, pg_temp as $$
declare
  v_missing text;
  v_dup text;
begin
  if public.current_role_name() is distinct from 'admin' then
    raise exception 'only an admin can decide' using errcode = '42501';
  end if;
  if not exists (select 1 from onboarding_runs where run_id = p_run_id and status = 'proposed') then
    raise exception 'only a proposed run can be approved or rejected' using errcode = '22023';
  end if;
  if p_decision = 'reject' then
    update onboarding_runs set status = 'rejected', reject_reason = left(p_reason, 300), decided_by = auth.uid(),
           decided_at = now() where run_id = p_run_id;
    return 'rejected';
  elsif p_decision <> 'approve' then
    raise exception 'decision must be approve or reject' using errcode = '22023';
  end if;
  -- The fields each column feeds: its own field, plus lon for a combined lat/long column.
  with fed as (
    select unified_field as field from onboarding_mappings where run_id = p_run_id and unified_field is not null
    union all
    select 'lon' from onboarding_mappings
     where run_id = p_run_id and unified_field = 'lat' and transform = 'latlong_lat'
  )
  select string_agg(f.field, ', ' order by f.sort) into v_missing
    from onboarding_fields f
   where f.required and not exists (select 1 from fed where fed.field = f.field);
  if v_missing is not null then
    raise exception 'required fields not mapped: %', v_missing using errcode = '22023';
  end if;
  with fed as (
    select unified_field as field from onboarding_mappings where run_id = p_run_id and unified_field is not null
    union all
    select 'lon' from onboarding_mappings
     where run_id = p_run_id and unified_field = 'lat' and transform = 'latlong_lat'
  )
  select string_agg(field, ', ') into v_dup from (select field from fed group by field having count(*) > 1) d;
  if v_dup is not null then
    raise exception 'fields mapped more than once: %', v_dup using errcode = '22023';
  end if;
  update onboarding_runs set status = 'approved', decided_by = auth.uid(), decided_at = now()
   where run_id = p_run_id;
  return 'approved';
end;
$$;

revoke all on function public.onboarding_decide(uuid, text, text) from public, anon;
grant execute on function public.onboarding_decide(uuid, text, text) to authenticated;

-- Rollback: re-run the onboarding_decide definition from 0007_15_source_onboarding.sql (same signature).
