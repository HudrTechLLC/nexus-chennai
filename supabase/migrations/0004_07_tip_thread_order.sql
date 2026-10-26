-- 0004_07 · Tip conversation order (fix for 0004_03). Owner: nexus-4 (Web).
-- Tipster messages are stored with their time coarsened to the day (J1), so ordering a thread by
-- `at` put a tipster's answer before the police message it replied to. Order by message_id
-- (an identity, so it always increases) instead. Same signature, grants unchanged.

create or replace function public.tip_status(p_code text, p_passphrase text)
returns jsonb
language plpgsql volatile security definer set search_path = public as $$
declare
  v text := public.tip_check(p_code, p_passphrase);
begin
  if v in ('not_found', 'locked') then
    return jsonb_build_object('ok', false, 'error', v);
  end if;
  return (
    select jsonb_build_object(
      'ok', true, 'tip_id', t.tip_id, 'status', public.tip_public_status(t.status), 'received_week', t.received_week,
      'messages', coalesce((select jsonb_agg(jsonb_build_object('sender', m.sender, 'text', m.text, 'on', m.at::date) order by m.message_id)
                            from public.tip_messages m where m.tip_id = t.tip_id), '[]'::jsonb))
    from public.tips t where t.tip_id = v);
end
$$;

-- Rollback: re-run the tip_status definition from 0004_03 (ordered by m.at).
