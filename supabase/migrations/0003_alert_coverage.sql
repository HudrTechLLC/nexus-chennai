-- 0003 · link_alerts.coverage (DECISIONS D-016). Owner: nexus-1.
-- Coverage = sum of the weights of factors that had data; shown on the alert card.
-- link_factors.evidence items may now carry {query, query_id} besides {view, row} (jsonb, no DDL).

alter table public.link_alerts
  add column if not exists coverage real check (coverage is null or coverage between 0 and 1);

-- Rollback:
--   alter table public.link_alerts drop column if exists coverage;
