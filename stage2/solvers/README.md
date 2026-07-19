<!--
  File: solvers/README.md
  Purpose: Which solver to submit and why, plus how to test it locally.
-->

# Stage 2 solvers

Three solvers live here. Submit one `solver.py` (Solo track, at most 500 KB).

| Solver | Approach | Recommended |
|---|---|---|
| [`hybrid/`](./hybrid/solver.py) | Deterministic first, model only as a last resort | Yes |
| [`gpt_oss_120b/`](./gpt_oss_120b/solver.py) | Model-led (gpt-oss-120b) | Superseded |
| [`gemma_4_31b/`](./gemma_4_31b/solver.py) | Model-led (gemma) | Superseded |

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
   method) and the judge's own error text fed back each round.

The Lean templates match the judge contract exactly:

```
true  : Goal = forall (G : Type) [Magma G], EquationLHS G -> EquationRHS G
false : Goal = exists (G : Type) (_ : Magma G), EquationLHS G and not EquationRHS G
```

A model-proposed counterexample is also re-verified in Python before it is
trusted, so the solver never forwards an unchecked `false` certificate.

## Test it locally before submitting

The Lean judge is what decides acceptance, so run the official harness (from
the [Stage 2 repository](https://github.com/SAIRcompetition/equational-theories-lean-stage2))
against this solver first:

```
bash scripts/setup.sh            # one-time Lean and judge setup
source .env.judge
python3 -m pipeline.runner \
  --submission <path>/stage2/solvers/hybrid \
  --problems examples/problems/sample_20.json
```

Read `pipeline/results/` and confirm the deterministic answers are accepted.
Submit only after the harness is clean.

## Submit

Upload `hybrid/solver.py` on the competition page (Submit Solver, Solo track),
or use the repository's `scripts/submit.py`. The submission is the single file;
nothing else in the folder is sent.
