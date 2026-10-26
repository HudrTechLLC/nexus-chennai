-- zetaris/40_feeds.sql · Synthetic news and social REST feeds (spec D1 #16-17, E5; WS1-16). Owner: nexus-2.
-- The API serves GET /mock-feeds/news and /mock-feeds/social (services/api/app/feeds.py) as {"items": [...]}.
-- Zetaris registers them as REST tables in Lightning database nexus_feeds and flattens them into views in
-- container `nexus` (created by 10_views.sql). Syntax: zetaris/getting-started @6a2fbaa, sections 5.2, 6.2, 12.1.
-- One statement per call; register.py strips the trailing semicolons and fills {{since}} / {{until}}.
-- v_news_mentions must stay in step with the q_news DuckDB twin in services/api/app/adapters/zetaris_queries_n2.py
-- (NEWS_DAYS = 4; alias -> station or ward; category_hint reported, not required).

CREATE LIGHTNING DATABASE nexus_feeds DESCRIBE BY "Nexus synthetic news and social feeds";

CREATE LIGHTNING REST TABLE rest_news FROM nexus_feeds REQUEST (
  endpoint "http://host.docker.internal:8000/mock-feeds/news?since={{since}}&until={{until}}",
  method "GET",
  http_encoding "URLENCODED",
  response_type "JSON",
  insecure_ssl "false"
) HEADER () BODY ();

CREATE LIGHTNING REST TABLE rest_social FROM nexus_feeds REQUEST (
  endpoint "http://host.docker.internal:8000/mock-feeds/social?since={{since}}&until={{until}}",
  method "GET",
  http_encoding "URLENCODED",
  response_type "JSON",
  insecure_ssl "false"
) HEADER () BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW news_items WITH CONTAINER nexus AS
SELECT i.article_id, i.outlet, CAST(i.published_at AS TIMESTAMP) AS published_at, i.headline, i.body,
       i.places_mentioned, i.url, i.synthetic
FROM nexus_feeds.rest_news LATERAL VIEW explode(items) e AS i
WHERE i.synthetic = true;

CREATE OR REPLACE SCHEMASTORE VIEW social_posts WITH CONTAINER nexus AS
SELECT i.post_id, i.platform, CAST(i.posted_at AS TIMESTAMP) AS posted_at, i.handle, i.text,
       i.places_mentioned, i.hashtags, i.synthetic
FROM nexus_feeds.rest_social LATERAL VIEW explode(items) e AS i
WHERE i.synthetic = true;

CREATE OR REPLACE SCHEMASTORE VIEW v_news_mentions WITH CONTAINER nexus AS
SELECT c.crime_id, n.article_id, first(n.headline) AS headline, first(n.outlet) AS outlet,
       first(n.published_at) AS published_at, first(n.url) AS url, min(a.canonical) AS matched_place,
       CAST(floor((unix_timestamp(first(n.published_at)) - unix_timestamp(c.occurred_from)) / 3600) AS INT) AS hours_after,
       max(instr(lower(n.headline), split(c.category, '_')[0]) > 0) AS category_hint
FROM nexus.v_crime_unified c
JOIN s3csv.place_aliases a ON (a.station_id = c.station_id OR a.ward_no = c.ward_no)
JOIN (SELECT article_id, headline, outlet, published_at, url, place
      FROM nexus.news_items LATERAL VIEW explode(places_mentioned) p AS place) n
  ON lower(trim(n.place)) = lower(trim(a.alias))
WHERE n.published_at >= c.occurred_from AND n.published_at < c.occurred_from + INTERVAL 4 DAYS
GROUP BY c.crime_id, n.article_id, c.occurred_from;

-- Hourly weather for v_context / q_context (spec D1 #18: Open-Meteo, real, no key). One series for the city
-- centre from the city pack; timezone=auto returns local times ("2026-10-10T21:00"), so `hour` joins on the
-- crime's local hour. Needs outbound HTTPS from the Zetaris container. Window = register.py --since/--until.
CREATE LIGHTNING REST TABLE rest_weather FROM nexus_feeds REQUEST (
  endpoint "https://api.open-meteo.com/v1/forecast?latitude={{city:map.center.1}}&longitude={{city:map.center.0}}&hourly=temperature_2m,precipitation,weather_code&timezone=auto&start_date={{since}}&end_date={{until}}",
  method "GET",
  http_encoding "URLENCODED",
  response_type "JSON",
  insecure_ssl "false"
) HEADER () BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW weather_hourly WITH CONTAINER nexus AS
SELECT substring(t, 1, 13) AS hour, hourly.temperature_2m[i] AS temperature_c,
       hourly.precipitation[i] AS precipitation_mm, hourly.weather_code[i] AS weather_code
FROM nexus_feeds.rest_weather LATERAL VIEW posexplode(hourly.time) e AS i, t;
