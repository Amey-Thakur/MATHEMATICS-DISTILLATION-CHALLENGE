<!--
  File: solvers/README.md
  Purpose: Which solver to submit, how it works, and how to test it locally.
-->

# Stage 2 solvers

Submit one `solver.py` (at most 500 KB). Each track accepts up to two
submissions, and either model may be chosen.

| Solver | Approach | Tracks | Recommended |
|---|---|---|---|
| [`hybrid/`](./hybrid/solver.py) | Deterministic first, model only as a last resort | Solo and Marathon | Yes |
| [`gpt_oss_120b/`](./gpt_oss_120b/solver.py) | Model-led (gpt-oss-120b) | Solo | Superseded |
| [`gemma_4_31b/`](./gemma_4_31b/solver.py) | Model-led (gemma) | Solo | Superseded |

## Why hybrid

The model-led solvers ask an LLM to write the Lean 4 proof, then hope the
judge accepts it. Lean proofs from a model are wrong often enough that the
judge rejects a large share of answers.

`hybrid/solver.py` inverts that. It proves what it can without the model, and
every deterministic answer is correct by construction:

1. **Counterexample search** (a `false` verdict). It searches finite magmas
   (Fin 2 and Fin 3 exhaustively, Fin 4 by constrained backtracking) for a
   table where the hypothesis holds and the goal fails. The witness is
   verified in Python before it is sent, so the judge's `decideFin!` only
   confirms a fact that is already checked. No tokens are spent.
2. **Collapse proof** (a `true` verdict). If the hypothesis forces every
   element equal, any goal follows from a one-line `all_eq` argument. No
   tokens are spent.
3. **Model fallback** (a `true` verdict that needs a real proof). Only here
   does it call the model, with a structural prompt (the MATCH then COLLAPSE
   method). In Solo the judge error is fed back each round; in Marathon a
   single guarded attempt is made per unsolved problem while the token
   budget allows.

On the official 20-problem sample, the deterministic stages alone answer 14,
with no tokens and no incorrect certificates.

## One file, both tracks

The same `solver.py` runs on either track. It reads the environment: when
`JUDGE_MARATHON_MANIFEST` is set it runs Marathon (manifest in, append-only
JSONL out, shared token budget); otherwise it runs Solo (stdin and stdout
JSON with interactive judge feedback). Deterministic answers cost no tokens,
which is exactly what Marathon's compressed budget rewards.

The Lean templates match the judge contract exactly:

```
true  : Goal = forall (G : Type) [Magma G], EquationLHS G -> EquationRHS G
false : Goal = exists (G : Type) (_ : Magma G), EquationLHS G and not EquationRHS G
```

## Test it locally before submitting

The Lean judge decides acceptance, so run the official harness (from the
[Stage 2 repository](https://github.com/SAIRcompetition/equational-theories-lean-stage2))
first.

```
bash scripts/setup.sh            # one-time Lean and judge setup
source .env.judge

# Solo
python3 -m pipeline.runner \
  --submission <path>/stage2/solvers/hybrid \
  --problems examples/problems/sample_20.json

# Marathon
python3 scripts/run_marathon_harness.py \
  --submission <path>/stage2/solvers/hybrid \
  --manifest examples/problems/marathon/normal_100.jsonl
```

Read `pipeline/results/` and confirm the deterministic answers are accepted.
Submit only after the harness is clean.

## Submit

On the competition page choose the track and model, then upload
`hybrid/solver.py` (Submit Solver). The submission is that single file;
nothing else in the folder is sent.
