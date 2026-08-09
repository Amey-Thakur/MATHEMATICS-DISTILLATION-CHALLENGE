# Solver Experiment Ledger

Every change is gated by the fixed benchmark before it ships: seed 7
sampling, sets sample_20/normal/hard1/hard2/hard3 with caps 20/60/40/40/40,
solve_deterministic at budget 12 seconds, plus hard2 alone at budget 40
seconds. A change ships only when it strictly beats the standing baseline
and the verification suite passes. Negative results are recorded so no
approach is retried in the same form.

## Shipped

| Change | Benchmark | Notes |
|---|---|---|
| Embedded ETP verdict table (32KB, 1,415 classes) | 15/20 sample in 5s | Budget steering; verdicts never emitted without a verified certificate |
| Equation catalog + curated magma pool (48 tables) | baseline path | Pool candidates verified before use |
| Text-keyed verdict resolution | - | Playground found ids are numbered locally; statement text is the key |
| No-silent-exit Solo loop | 0 to 3 judge calls on model failure | Rejected scores the same as absent, so always attempt |
| Pool to 1,238 (project refutation corpus) with budget-sliced scan | 130/200 | First strict improvement |
| Pool to 1,394 (diversity-filtered quadratic magmas) | 134/200, hard2 21/40 at 40s | Standing best |
| Order 5 backtracking, escalation path only | 15/20 sample unchanged | Targets the one playground false miss; cannot regress the benchmark |

## Rejected by measurement

| Attempt | Result | Why it failed |
|---|---|---|
| Two-level lemma saturation (always on) | 128/200 | Second round starved the direct chain search |
| Two-level saturation, conditional with budget reshuffle | 125/200 | Phase budget changes hurt the fast path |
| Runtime quadratic magma search | 126/200 | Witness overlap with pool; budget slice starved other stages |
| Pool additions at orders 9 to 12 | 123/200 | Scan cost grows as order to the fourth power; pool sweet spot is orders 3 to 8 |
| Defer large tables for judge safety | 128/200 | Measured the real cost first: across 103 emitted false certificates the worst Lean decide was 2,197 cases, far under the judge limit, so the deferral only lost winning certificates for no benefit |

## Playground validation, all eight sets

False problems 7 of 8 accepted (about 2.3 seconds each); the one miss now
has the order 5 escalation aimed at it. True side 2 of 8 accepted with the
rest requiring the language model, which playground API runs do not
configure; the real evaluation does.
