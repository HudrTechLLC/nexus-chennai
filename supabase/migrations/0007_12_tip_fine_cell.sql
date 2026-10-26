-- 0007_12 · Tips at H3 resolution 8, 9 or 10 (WS4-15 part C; nexus-6, contract agreed with nexus-2).
--
-- The tip form now lets the tipster pick a finer area (r9 by default, r8 or r10). Every existing reader of
-- tips.approx_cell assumes r8: submit_tip's weekly cap, tip_nearby_crimes (c.h3_r8 = t.approx_cell), the
-- console map tips layer, the Zetaris tips_v join (zetaris_queries_n1) and the 0003 column grant to the
-- Zetaris reader. So approx_cell keeps meaning "the r8 cell" (now the PARENT of what was picked) and none of
-- those readers change; the cell exactly as picked goes in a new column, approx_cell_fine.
--
-- Postgres has no h3 extension here, so the r8 parent is computed with bit operations (h3_parent_r8): set
-- the resolution field (bits 52-55) to 8 and every digit after the 8th (digits 9-15, the low 21 bits) to 7,
-- the "unused" digit. Checked against the h3 library's cell_to_parent in tests/console/test_tip_fine_cell_live.py.

-- ---------- column ----------
alter table public.tips add column if not exists approx_cell_fine text;
alter table public.tips drop constraint if exists tips_approx_cell_fine_check;
alter table public.tips add constraint tips_approx_cell_fine_check
  check (approx_cell_fine is null or approx_cell_fine ~ '^8[89a][0-9a-f]{13}$');
comment on column public.tips.approx_cell is 'H3 r8 cell (the parent of approx_cell_fine when the tipster picked a finer area)';
comment on column public.tips.approx_cell_fine is 'H3 cell at the resolution the tipster picked (r8, r9 or r10); console only';

-- ---------- r8 parent ----------
create or replace function public.h3_parent_r8(p_cell text)
returns text
language plpgsql immutable strict set search_path = public, pg_temp as $$
declare
  v bigint;
begin
  if p_cell !~ '^8[89a][0-9a-f]{13}$' then
    raise exception 'not an H3 cell at resolution 8, 9 or 10: %', p_cell using errcode = '22023';
  end if;
  v := ('x' || lpad(p_cell, 16, '0'))::bit(64)::bigint;
  v := (v & ~(15::bigint << 52)) | (8::bigint << 52) | 2097151;   -- res := 8; digits 9..15 := 7
  return lpad(to_hex(v), 15, '0');
end
$$;
revoke all on function public.h3_parent_r8(text) from public;
grant execute on function public.h3_parent_r8(text) to anon, authenticated, service_role;

-- ---------- submit_tip: same signature; accepts r8-r10, stores the r8 parent + the fine cell ----------
create or replace function public.submit_tip(
  p_appeal text, p_category text, p_text text, p_cell text, p_follow_up boolean,
  p_code text, p_passphrase text, p_media jsonb, p_tz text, p_about text default null
) returns jsonb
language plpgsql volatile security definer set search_path = public, pg_temp as $$
declare
  v_week  text := public.iso_week(now(), p_tz);
  v_id    text;
  v_hash  text;
  v_about text;
  v_r8    text;   -- the r8 parent: what every existing reader of approx_cell assumes
  m       jsonb;
  i       int := 0;
begin
  if p_category is null or p_category not in ('vehicle_seen', 'person_seen', 'have_cctv', 'item_for_sale', 'something_else') then
    raise exception 'invalid category' using errcode = '22023';
  end if;
  if p_text is null or length(btrim(p_text)) < 3 or length(p_text) > 4000 then
    raise exception 'text must be 3 to 4000 characters' using errcode = '22023';
  end if;
  if p_cell is not null and p_cell !~ '^8[89a][0-9a-f]{13}$' then
    raise exception 'area must be an H3 cell at resolution 8, 9 or 10' using errcode = '22023';
  end if;
  v_r8 := public.h3_parent_r8(p_cell);
  if p_appeal is not null and not exists (
       select 1 from public.public_incidents where public_incident_id = p_appeal and status = 'published') then
    raise exception 'unknown appeal' using errcode = '22023';
  end if;
  if p_about is not null then
    select pool.crime_id into v_about from public.public_card_pool(90) pool
     where p_about ~ '^PC-[0-9A-F]{12}$' and public.crime_public_id(pool.crime_id) = p_about limit 1;
    if v_about is null then
      raise exception 'unknown crime' using errcode = '22023';
    end if;
  end if;
  if jsonb_typeof(coalesce(p_media, '[]'::jsonb)) <> 'array' or jsonb_array_length(coalesce(p_media, '[]'::jsonb)) > 5 then
    raise exception 'at most 5 files' using errcode = '22023';
  end if;
  -- per-cell weekly cap (throttling without identity, J1), counted on the r8 parent so finer cells cannot dodge it
  if v_r8 is not null and (select count(*) from public.tips where approx_cell = v_r8 and received_week = v_week) >= 200 then
    raise exception 'too many tips for this area this week, please try later' using errcode = 'P0001';
  end if;

  if coalesce(p_follow_up, false) then
    if p_code is null or p_code !~ '^[A-HJ-NP-Z2-9]{8}$' then
      raise exception 'invalid tip code' using errcode = '22023';
    end if;
    if p_passphrase is null or length(p_passphrase) < 8 or length(p_passphrase) > 128 then
      raise exception 'passphrase must be 8 to 128 characters' using errcode = '22023';
    end if;
    v_id := 'TIP-' || p_code;
    v_hash := extensions.crypt(p_passphrase, extensions.gen_salt('bf', 12));
  else
    v_id := 'TIP-' || upper(encode(extensions.gen_random_bytes(5), 'hex'));
    v_hash := null;
  end if;

  insert into public.tips (tip_id, public_incident_id, about_crime_id, channel, category, text, follow_up_enabled,
                           tip_code_hash, guard, approx_cell, approx_cell_fine, received_week, status, synthetic)
  values (v_id, p_appeal, v_about, 'web', p_category, btrim(p_text), coalesce(p_follow_up, false),
          v_hash, null, v_r8, p_cell, v_week, 'new', false);

  for m in select * from jsonb_array_elements(coalesce(p_media, '[]'::jsonb)) loop
    i := i + 1;
    if (m ->> 'path') !~ '^tips/[0-9a-f-]{36}\.(jpg|png|webp|mp3|m4a|ogg|webm)$'
       or (m ->> 'kind') not in ('image', 'audio') then
      raise exception 'invalid file reference' using errcode = '22023';
    end if;
    insert into public.tip_media (media_id, tip_id, kind, path, exif_stripped, faces_blurred, synthetic)
    values (v_id || '-M' || i, v_id, m ->> 'kind', m ->> 'path', true,
            coalesce((m ->> 'faces_blurred')::boolean, false), false);
  end loop;

  return jsonb_build_object('tip_id', v_id, 'received_week', v_week);
exception
  when unique_violation then
    raise exception 'tip code already used, please try again' using errcode = 'P0001';
end
$$;

revoke all on function public.submit_tip(text, text, text, text, boolean, text, text, jsonb, text, text) from public;
grant execute on function public.submit_tip(text, text, text, text, boolean, text, text, jsonb, text, text) to anon, authenticated;

-- Rollback:
--   re-run the submit_tip definition and grants from 0007_11;
--   drop function if exists public.h3_parent_r8(text);
--   alter table public.tips drop constraint if exists tips_approx_cell_fine_check;
--   alter table public.tips drop column if exists approx_cell_fine;
