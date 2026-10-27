# Real-world validation: why it is not done, and the plan

Judges' strongest request (fix #23): show value beyond our own synthetic, planted data. We could not do this before
submission, and we say so plainly.

## Why not yet
- Real FIRs, suspect details and CCTV are personal and sensitive. Using them needs a data-sharing agreement with a
  police unit, an ethics and privacy review, and access controls we have not been granted.
- Public crime datasets we know of (city open-data portals) publish incidents but not which incidents a single
  offender committed, so they cannot score cross-station linking.
- Every number we publish is therefore on synthetic data with planted truth, and every limitation that follows from
  that is listed in the README.

## What partly covers the gap today
- A pre-registered Nemotron-alone baseline that our pipeline does not beat on the pairs it saw (published).
- Pre-registered planted tests of the Skeptic, including one it failed (0/24, published).
- An independent look-alike test written without reading the generator's plant code (#19, in progress).
- A timed analyst task protocol (`TIMED_TASK_PREREG.md`).

## Pilot plan (after the hackathon)
1. **Blinded alert review (2–4 weeks):** a crime-analysis unit reviews a sample of Nexus alerts from their own closed
   cases, with links they already confirmed or rejected hidden; we report precision by band and time per review.
2. **Shadow mode (1–3 months):** Nexus runs read-only next to the unit's normal process on new FIRs; no alert reaches
   an officer unless the analyst asks. We report links found earlier than the normal process, and false-alert load.
3. **Go/no-go:** only if HIGH precision stays above 90% and analysts report net time saved. People keep every
   decision throughout.

Data stays inside the police network; Nexus reads it through Zetaris named queries, so no copy leaves the source
systems.
