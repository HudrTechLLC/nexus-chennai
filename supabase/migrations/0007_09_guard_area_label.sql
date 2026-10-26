-- 0007_09 · The appeal publish guard also checks area_label (nexus-5).
-- Found in the live appeal run on 26 Oct: a Sanitiser draft's area_label was "Adyar (near VHS Hospital,
-- Adyar area)", which carries the case landmark. 0007_08 checked only title, summary and looking_for, and
-- the console editor cannot edit area_label, so the landmark would have been published. The label is now
-- checked with the same pattern and per-case rules. Everything else is the 0007_08 guard, unchanged.
-- (The Sanitiser's area_label bug itself was fixed in #194; this stops any label that still leaks.)

create or replace function public.public_incidents_publish_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_leak text;
  v_item text;
  v_role text;
  v_station text;
begin
  if new.status <> 'published' then
    return new;
  end if;
  v_leak := coalesce(public.appeal_text_leaks(new.title), public.appeal_text_leaks(new.summary),
                     public.appeal_text_leaks(new.area_label));
  if v_leak is null then
    foreach v_item in array coalesce(new.looking_for, '{}'::text[]) loop
      v_leak := public.appeal_text_leaks(v_item);
      exit when v_leak is not null;
    end loop;
  end if;
  if v_leak is null and new.crime_id is not null then
    v_leak := coalesce(public.appeal_case_leak(new.crime_id, new.title), public.appeal_case_leak(new.crime_id, new.summary),
                       public.appeal_case_leak(new.crime_id, new.area_label));
    if v_leak is null then
      foreach v_item in array coalesce(new.looking_for, '{}'::text[]) loop
        v_leak := public.appeal_case_leak(new.crime_id, v_item);
        exit when v_leak is not null;
      end loop;
    end if;
  end if;
  if v_leak is not null then
    raise exception 'appeal text contains a %; remove it before publishing', v_leak using errcode = 'check_violation';
  end if;
  if auth.uid() is not null then
    select p.role, p.station_id into v_role, v_station from public.profiles p where p.user_id = auth.uid();
    if v_role is null then
      raise exception 'only a police user can publish an appeal' using errcode = 'insufficient_privilege';
    end if;
    new.approved_by := v_role || ':' || coalesce(v_station, auth.uid()::text);
  elsif new.approved_by is null then
    raise exception 'approved_by is required to publish' using errcode = 'not_null_violation';
  end if;
  if tg_op = 'INSERT' or old.status is distinct from 'published' then
    new.published_at := now();
  else
    new.published_at := old.published_at;
  end if;
  return new;
end
$$;
revoke all on function public.public_incidents_publish_guard() from public, anon;

-- Rollback:
--   re-run the public_incidents_publish_guard definition from 0007_08_appeal_case_leaks.sql
