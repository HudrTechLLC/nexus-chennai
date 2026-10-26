-- 0003 · zetaris_reader sees only safe tip columns (DECISIONS D-023, R1/J1). Owner: nexus-1.
-- Tips hold a passphrase hash and raw untrusted text. Zetaris federates tips through the
-- datasource view tips_v; this column-level grant makes sure the role itself cannot read the
-- hash, the raw body or the follow-up flag even with a hand-written query.

revoke select on public.tips from zetaris_reader;
grant select (tip_id, public_incident_id, channel, category, guard, approx_cell, received_week, status,
              source, source_row_id, synthetic)
  on public.tips to zetaris_reader;

-- tip_media and tip_messages stay ungranted to zetaris_reader.

-- Rollback:
--   revoke select on public.tips from zetaris_reader;
--   grant select on public.tips to zetaris_reader;
