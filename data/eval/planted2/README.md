# Planted false-link set #2: eval-only sample bundle

Synthetic. Used only by the Skeptic's planted false-link retest (set #2,
`engg/docs/eval/planted_skeptic_cases_set2.json`). Nothing else reads it: the app, the judge path and set #1 use
`data/sample`. It is selected only when `NEXUS_SAMPLE_DIR=data/eval/planted2/sample` is set.

- **Built from:** generator seed **1027** (data/sample is seed 42), with every series as core:
  `python -m data.generator --seed 1027 --out <tmp>` then
  `python -m data.generator.sample --from <tmp> --out data/eval/planted2/sample --core-series all`.
  This takes about 12 minutes and needs no database. `sb/crime_features.parquet` is empty, so every crime uses its
  series' generator-truth MO (`features_source = generator_truth`).
- **Why a separate bundle:** set #1 already uses all but 3 of data/sample's eligible series crimes, and those 3 are in
  different series. Fresh twins need new crimes, and adding them to data/sample would change the judge path.
- **Pinned:** the bundle's file-tree sha256 and the case file's sha256 are both asserted in
  `tests/eval/test_planted_skeptic_set2.py`.
- **Crime ids** follow the generator's numbering, so an id here can match a seed-42 id while naming a different
  crime. Set #1's ids, the protected ids and the judge-input ids are excluded anyway.
