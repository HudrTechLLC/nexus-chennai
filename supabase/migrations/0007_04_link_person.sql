-- 0007_04 · Link known accused / suspects (and described people) to a case (spec CAP-01, CAP-05; nexus-5,
-- approved by the chief). Officers have no INSERT on persons or person_links (0002), so one
-- security-definer RPC does it, with the same rule as every other case write:
--   * public.can_write_crime(crime_id): admin and supervisor anywhere, a station officer only on a
--     case of their own station (0002);
--   * names and aliases are stored only for accused and suspects. Victims, witnesses and complainants
--     are linked by descriptors alone, so their identity never enters the register (J5, B9);
--   * every link is written to audit_log (append-only, 0007_03).
-- It links an existing person (person_id) or creates one. It never edits or removes a person or a
-- link (no deletes on shared data without the chief's OK).

create or replace function public.link_person(p jsonb) returns text
language plpgsql security definer set search_path = public as $$
declare
  v_crime   text := p->>'crime_id';
  v_role    text := p->>'role';
  v_person  text := nullif(trim(p->>'person_id'), '');
  v_name    text := nullif(trim(p->>'name'), '');
  v_aliases text[];
  v_desc    jsonb := coalesce(p->'descriptors', '{}'::jsonb);
  v_ward    integer := nullif(p->>'residence_ward', '')::integer;
  v_key     text;
  v_created boolean := false;
  v_allowed_desc text[] := array['height_band', 'build', 'age_band', 'gender', 'marks', 'clothing', 'complexion', 'hair'];
begin
  if v_crime is null or not exists (select 1 from crimes where crime_id = v_crime) then
    raise exception 'unknown case' using errcode = '22023';
  end if;
  if not public.can_write_crime(v_crime) then
    raise exception 'you can link people only to cases your station may write' using errcode = '42501';
  end if;
  if v_role is null or v_role not in ('accused', 'suspect', 'victim', 'witness', 'complainant') then
    raise exception 'role must be accused, suspect, victim, witness or complainant' using errcode = '22023';
  end if;
  if jsonb_typeof(v_desc) <> 'object' then raise exception 'descriptors must be an object' using errcode = '22023'; end if;
  for v_key in select jsonb_object_keys(v_desc) loop
    if not v_key = any (v_allowed_desc) then raise exception 'unknown descriptor %', v_key using errcode = '22023'; end if;
    if length(v_desc->>v_key) > 80 then raise exception 'descriptor % is too long', v_key using errcode = '22023'; end if;
  end loop;
  select coalesce(array_agg(left(trim(a), 60)) filter (where trim(a) <> ''), '{}') into v_aliases
    from jsonb_array_elements_text(coalesce(p->'aliases', '[]'::jsonb)) a;
  if cardinality(v_aliases) > 10 then raise exception 'too many aliases' using errcode = '22023'; end if;
  if v_role in ('victim', 'witness', 'complainant') and (v_name is not null or cardinality(v_aliases) > 0) then
    raise exception 'victims, witnesses and complainants are linked by description only, without a name' using errcode = '22023';
  end if;
  if v_name is not null and length(v_name) > 120 then raise exception 'name is too long' using errcode = '22023'; end if;
  if v_ward is not null and not exists (select 1 from wards where ward_no = v_ward) then
    raise exception 'unknown ward' using errcode = '22023';
  end if;

  if v_person is not null then
    if not exists (select 1 from persons where person_id = v_person) then
      raise exception 'unknown person' using errcode = '22023';
    end if;
    -- A named person (an accused elsewhere, a history-sheeter) must not become a victim, witness
    -- or complainant through the link: that would put a protected identity on the case (J5).
    if v_role in ('victim', 'witness', 'complainant')
       and exists (select 1 from persons where person_id = v_person and (name is not null or cardinality(aliases) > 0)) then
      raise exception 'a named person cannot be linked as victim, witness or complainant; link a described person instead'
        using errcode = '22023';
    end if;
  else
    if v_name is null and v_desc = '{}'::jsonb then
      raise exception 'give a name (accused or suspect) or at least one descriptor' using errcode = '22023';
    end if;
    v_person := 'P-' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 12);
    insert into persons (person_id, name, aliases, descriptors, residence_ward, source, source_row_id, synthetic)
    values (v_person, v_name, v_aliases, v_desc, v_ward, 'sb.persons', gen_random_uuid()::text, true);
    v_created := true;
  end if;

  insert into person_links (person_id, crime_id, role, synthetic) values (v_person, v_crime, v_role, true)
  on conflict (person_id, crime_id, role) do nothing;

  -- who = auth.uid() explicitly (the column default is the same; stated here so the actor is never lost).
  insert into audit_log (who, what, object_type, object_id, details)
  values (auth.uid(), 'link_person', 'crime', v_crime, jsonb_build_object('person_id', v_person, 'role', v_role, 'created_person', v_created));
  return v_person;
end
$$;
revoke all on function public.link_person(jsonb) from public, anon;
grant execute on function public.link_person(jsonb) to authenticated;

-- Rollback:
--   drop function if exists public.link_person(jsonb);
