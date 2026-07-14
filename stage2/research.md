# Stage 2 Research Report

## 1. What Stage 2 Actually Requires

Stage 2 is not about predicting true/false. It is about producing machine-verifiable Lean 4 proof certificates. The judge is entirely deterministic. No partial credit, no probabilistic scoring.

You submit one file: `solver.py`, max 500 KB.

For each problem pair (Eq1, Eq2), the solver must output one of:
- **True certificate**: A Lean 4 proof that Eq1 implies Eq2 over all magmas.
- **False certificate**: A Lean 4 proof that there exists a finite magma where Eq1 holds but Eq2 fails.

The judge returns exactly one of five statuses:
- `accepted` (you scored)
- `unparsed` (bad JSON)
- `malformed` (schema violation)
- `incomplete_proof` (used sorry/admit/banned axioms)
- `incorrect` (valid Lean but fails type-checking or the proof is wrong)

## 2. Problem Domain

The problems deal with **equational implications over magmas**. A magma is a set with a single binary operation (written as ◇). There is no associativity, commutativity, or identity assumed.

Equations look like:
```
x = (y ◇ (z ◇ w)) ◇ (u ◇ v)
```

The question: does Equation 1 imply Equation 2 for ALL magmas?

The law list contains 4694 laws of order 4 or less, plus roughly 62,000 laws of order 5. The private evaluation set is drawn from this corpus and includes order-5 laws, so the solver cannot hardcode answers for a fixed subset.

## 3. Two Tracks

### Solo Track
- One problem per solver subprocess. Fresh process each time.
- 3600 seconds wall-clock per problem.
- LLM calls: 65,536 max output tokens per call.
- Lean code submissions: max 100 KB per call.
- Communication: stdin/stdout JSON. The proxy reads your `PROMPT` constant via AST parsing.

### Marathon Track
- N problems per solver subprocess (reference N=100).
- Compressed global budget: `compression_ratio * N * 600s` (default compression_ratio=0.5, so roughly 30,000s for 100 problems).
- Communication: file-based manifest in, append-only JSONL out.
- LLM calls via a local HTTP proxy using the OpenAI SDK.
- This track rewards triage, caching, and cross-problem reasoning.

## 4. The Lean 4 Judge Internals

The judge provides four custom imports:
1. **JudgeProblem** - Auto-generated per problem. Binds `EquationLHS`, `EquationRHS`, and `Goal`.
2. **JudgeDecide.DecideBang** - Provides `decideFin!` (which is just `decide` under the hood).
3. **JudgeFinOp.MemoFinOp** - Provides `finOpTable` which converts a JSON string like `"[[0,1],[1,0]]"` into `Fin n -> Fin n -> Fin n`.
4. **JudgeMagma.Magma** - Defines the `Magma` class and `◇` operator.

For a **true certificate**, `Goal` expands to:
```lean
∀ (G : Type) [Magma G], EquationLHS G → EquationRHS G
```

For a **false certificate**, `Goal` expands to:
```lean
∃ (G : Type) (_ : Magma G), EquationLHS G ∧ ¬ EquationRHS G
```

### False Certificate Template
```lean
import JudgeProblem
import JudgeDecide.DecideBang
import JudgeFinOp.MemoFinOp
open MemoFinOp

def submission : Goal := by
  let m : Magma (Fin 2) := {
    op := finOpTable "[[0,0],[1,1]]"
  }
  refine ⟨Fin 2, m, ?_⟩
  decideFin!
```

### True Certificate Template
```lean
import JudgeProblem

def submission : Goal := by
  intro G _ h
  intro x y z      -- goal variables
  calc
    ...             -- prove the equation using h
```

### Banned Tokens
`sorry`, `admit`, `sorryAx`, `dbg_trace`, `dbgTrace`, `run_tac`, `mkSorry`, `initialize`, `builtin_initialize`

### Proof Compilation Timeout
300 seconds per proof through the pipeline (120s if running verify.py directly).

### False Certificate Size Limit
20,000 bytes max for false certificates.

## 5. The Reference Solvers (What Already Works)

The official repo ships 6 demo solvers. Understanding them is critical because they define the baseline you need to beat.

### Solo Baseline
- Brute-force search for counterexamples on Fin 2 and Fin 3.
- Singleton proof (if hypothesis forces all elements equal).
- Generic LLM fallback with retry loop.

### Solo Opnorm (Flagship)
This is the most sophisticated reference solver at ~188 KB. It implements:
1. **16 deterministic proof strategies** before touching the LLM.
2. Exhaustive counterexample search on Fin 2-7.
3. Structured table generation (constant, modular arithmetic, projection, XOR, permutation, product, semilattice, selective, nilpotent, band-like tables).
4. Backtracking search with constraint propagation.
5. Random table sampling for Fin 4-7.
6. Singleton collapse detection.
7. Direct proof by substitution search.
8. Calc-chain proof by BFS over h-instantiations.
9. Compound calc-chain proof (substituting compound terms into h arguments).
10. `rw` chain proofs.
11. `congr_arg` iterated proofs.
12. `simp only [h]` and `simp only [← h]`.
13. `simp` with derived constancy lemmas.
14. `rw` followed by `simp`.
15. Specialized simp with self-substituted hypothesis.
16. `have` chain proofs using constancy/independence lemmas.

For the LLM fallback, it sends a structured MATCH-COLLAPSE prompt with:
- Constancy analysis (free variables on one side of h only)
- BFS near-miss search results
- Concrete h-instantiations
- Equation analysis (tree shape, structural similarity)
- Worked examples

### Marathon Baseline
- Sequential brute-force, no LLM. Clears roughly 40-50% of `normal` at zero token cost.

### Marathon Triage
- Sorts problems by estimated difficulty.
- Pass A: brute-force (free).
- Pass B: LLM with medium reasoning effort.
- Pass C: retries unsolved Pass B problems with bumped reasoning effort.

### Marathon Fewshot
- Accumulates winning patterns across problems.
- Prepends successful proofs as few-shot examples to later LLM prompts.
- Cross-problem state transfer (only possible in Marathon).

## 6. Reference Problem Sets

| Set | Size | True/False | Notes |
|-----|------|-----------|-------|
| `normal` | 1000 | 500/500 | Reference distribution. Start here. |
| `hard1` | 69 | 24/45 | Tightly packed pairs, high compute per row. |
| `hard2` | 200 | 100/100 | Where easy patterns fail. |
| `hard3` | 400 | 195/205 | Highest difficulty in the public split. |
| `sample_20` | 20 | mixed | Smoke test. |
| `sample_200` | 200 | 100/100 | Quick dev loop. |

The private evaluation set is separate and includes order-5 laws.

## 7. LLM Configuration

The organizer pins the model and parameters:
- **Model**: `openai/gpt-oss-120b`
- **Provider**: `deepinfra/bf16`
- **Max output tokens**: 65,536
- **Temperature**: 0.0
- **Reasoning effort**: medium
- **Seed**: 0 (deterministic)

You cannot change the model or its parameters. Your only control is the prompt and when/how you call it.

## 8. Key Mathematical Observations

### Why Most Implications Are False
For random pairs of equations over magmas, the vast majority of implications fail. A counterexample on Fin 2, 3, or 4 almost always exists. This is the single most important fact for solver design.

### The Constancy Lemma
If a variable appears on only one side of the hypothesis equation, the other side is independent of that variable. For example, if `x = y ◇ (z ◇ w)` and `w` appears only on the RHS, then for any fixed `x, y, z`, the value `y ◇ (z ◇ w)` is the same regardless of `w`. This yields:

```
(h x y z w1).symm.trans (h x y z w2)
```

which proves `y ◇ (z ◇ w1) = y ◇ (z ◇ w2)`.

This is the foundational proof technique for true implications in this domain.

### The MATCH-COLLAPSE Pattern
Almost all provable implications follow a 2-step pattern:
1. **MATCH**: Substitute compound terms into h's free variables so the resulting equation's structure aligns with the goal.
2. **COLLAPSE**: Use constancy to simplify the unneeded parts using `congr_arg`.

### Direct Substitution
Some goals are simply h with a specific variable mapping. The solver should check all permutations of goal variables against h's argument positions.

### Chaining h Applications
Some proofs require applying h multiple times in sequence (a calc chain). BFS over the space of h-instantiations can find these paths deterministically.

## 9. Strategy for Maximizing Score

### Priority Order (based on compute cost)

1. **Deterministic false certificates first** (zero LLM cost).
   - Exhaustive search on Fin 2-3.
   - Structured table library on Fin 2-7.
   - Backtracking search with constraint propagation on Fin 4-5.
   - Random sampling on Fin 4-7.
   - This alone handles roughly 50% of all problems.

2. **Deterministic true proofs** (zero LLM cost).
   - Direct substitution search.
   - Singleton collapse.
   - `simp only [h]` / `simp only [← h]`.
   - Calc-chain BFS (with bare variables, then compound terms).
   - Constancy-based proofs.
   - `rw` chain proofs.
   - This handles another 10-20% of problems.

3. **LLM-assisted proofs** (expensive).
   - Only fire after deterministic methods fail.
   - Feed the LLM structured analysis (constancy, BFS near-misses, tree shape matching).
   - Use a tight self-reflection loop: parse Lean errors, feed them back.
   - Budget awareness: stop after N retries.

### Marathon-Specific Advantages
- Triage: sort problems by estimated difficulty (number of variables, tree depth).
- Clear the easy ones first (brute-force pass is free).
- Accumulate successful proof patterns as few-shot examples.
- Cross-problem caching: if you proved Eq1 -> Eq3 and Eq3 -> Eq2, you can compose them.

## 10. Where to Beat the Reference Solver

The opnorm reference solver is strong but has clear gaps:

1. **Counterexample search depth**: It searches up to Fin 7 with structured tables but does not use SAT/SMT solvers. A Z3 or Mace4-style approach could find counterexamples on Fin 8-16 that the brute-force misses.

2. **True proof automation**: The BFS depth is limited. A deeper symbolic rewriting engine (term rewriting system) could find longer proof chains.

3. **Prompt quality**: The MATCH-COLLAPSE prompt is good but dense. A more targeted, per-equation-structure prompt could improve LLM accuracy.

4. **Self-reflection**: The opnorm solver parses Lean errors but the repair logic is basic. A more systematic error-driven retry (extracting the exact goal state from the error, showing the LLM what Lean expects vs what it got) would improve success rates.

5. **Order-5 equations**: The reference solver does not special-case the larger equation set. Order-5 equations have deeper trees and more variables, so the search spaces explode. Adaptive strategies (e.g., increasing Fin size only for order-5) could help.

6. **Pre-computation**: The 500 KB solver can embed pre-computed data. A lookup table of known counterexamples or proof patterns for common equation pairs could bypass search entirely.

## 11. Implementation Roadmap

### Phase 1: Environment Setup (Week 1)
- Set up WSL 2 on Windows.
- Install elan, Lean 4 toolchain, and build the judge modules.
- Run `bash scripts/setup.sh` and verify with `python3 scripts/run_harness.py`.
- Run the baseline solver on `sample_20.json` to confirm end-to-end flow.

### Phase 2: Deterministic Foundation (Weeks 2-3)
- Port and improve the opnorm counterexample search.
- Add SAT-based counterexample generation (encoding the equation constraints as boolean satisfiability problems).
- Implement a deeper BFS/DFS for calc-chain proofs.
- Implement the constancy lemma generator.
- Target: solve 70%+ of `normal` without LLM calls.

### Phase 3: LLM Integration (Weeks 3-4)
- Design the prompt template. Study what makes the opnorm MATCH-COLLAPSE prompt effective and where it fails.
- Implement the self-reflection loop with structured error parsing.
- Test on `hard1` and `hard2`.

### Phase 4: Marathon Optimization (Weeks 4-5)
- Implement triage ordering (estimate difficulty before solving).
- Build the few-shot cache.
- Implement cross-problem composition.
- Tune the compression ratio and budget allocation.

### Phase 5: Hardening (Weeks 5-6)
- Run full evaluation on `normal` (1000 problems).
- Profile failure modes. Categorize unsolved problems.
- Embed pre-computed lookup tables in solver.py.
- Run on `hard3` (400 problems) as the final stress test.

## 12. Open Questions

- What is the exact private evaluation set composition? (True/false ratio? Order-5 inclusion rate?)
- How does the `gpt-oss-120b` model perform on Lean 4 code compared to other models? (We cannot change it, but understanding its failure modes helps craft better prompts.)
- Is there a corpus of known implications from the Equational Theories Project that could be embedded as a lookup table?
- What is the practical upper bound on `Fin n` size for `decideFin!` within 300 seconds? (Likely around Fin 8-10, but this needs benchmarking.)
- Can we use Mathlib tactics (available via the judge's LEAN_PATH) for certain proof patterns? The reference solvers barely touch Mathlib.

## 13. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Lean compilation timeouts on complex proofs | High | Medium | Keep proofs simple. Prefer small Fin types for false certs. |
| LLM produces syntactically invalid Lean | High | Low | Robust parsing, cleanup, and retry loop. |
| Private eval set has different difficulty distribution | Medium | High | Test on all public sets. Do not overfit to `normal`. |
| 500 KB solver size too small for lookup tables | Low | Medium | Compress. Use only the highest-value entries. |
| Budget exhaustion in Marathon before solving hard problems | Medium | High | Solve cheap problems first. Strict triage. |

## 14. Deadline

**August 31, 2026, 23:59 AoE**

That gives roughly 7 weeks from today (July 14, 2026).
