# Stage 2 Solver Architecture

## Overview

The solver is a single `solver.py` file (max 500 KB) that communicates with the organizer's proxy via stdin/stdout JSON (Solo) or file-based JSONL (Marathon). It must support both tracks from one source file. The track is selected by checking the `JUDGE_MARATHON_MANIFEST` environment variable.

## Execution Pipeline

```
Problem arrives
    │
    ▼
┌─────────────────────────┐
│  1. Parse equations      │  Extract AST, variables, LHS/RHS
│     (microseconds)       │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  2. Counterexample       │  Structured tables (Fin 2-7)
│     search               │  Exhaustive (Fin 2-3)
│     (0-30 seconds)       │  Backtracking (Fin 4-5)
│                          │  Random sampling (Fin 4-7)
└────────────┬────────────┘
             │ found? → emit false cert → done
             │ not found? ↓
             ▼
┌─────────────────────────┐
│  3. Deterministic        │  Direct substitution
│     proof search         │  Singleton collapse
│     (0-10 seconds)       │  simp only [h]
│                          │  Calc-chain BFS
│                          │  Constancy lemmas
│                          │  rw chains
└────────────┬────────────┘
             │ accepted? → done
             │ not found? ↓
             ▼
┌─────────────────────────┐
│  4. LLM-assisted         │  Structured prompt with:
│     proof generation     │    - Constancy analysis
│     (30-3000 seconds)    │    - BFS near-miss hints
│                          │    - h-instantiations
│                          │    - Equation structure
│                          │  Self-reflection loop:
│                          │    - Parse Lean error
│                          │    - Feed back to LLM
│                          │    - Retry up to N times
└────────────┬────────────┘
             │ accepted? → done
             │ budget exhausted? → skip
             ▼
        Problem unsolved
```

## Component Details

### 2a. Counterexample Generator

The false certificate path. This is the most important component because the vast majority of implications are false, and counterexample generation costs zero LLM tokens.

**Table library**: Pre-computed structured tables that satisfy many common equations. These include constant operations, modular arithmetic, projections, semilattices, XOR, nilpotent structures, band-like operations, rectangular bands, and polynomial tables. The reference opnorm solver generates roughly 500-2000 candidate tables per Fin size.

**Exhaustive search**: Enumerate all possible operation tables on Fin 2 (16 tables) and Fin 3 (19,683 tables). Check each one against both equations.

**Backtracking search**: For Fin 4-5, use constraint propagation. Fill the table cell by cell. After placing each value, check if any instantiation of Eq1 is already violated. If so, backtrack immediately.

**Random sampling**: For Fin 4-7, generate random tables and test them. The reference solver runs 10,000 random tables per Fin size.

**Output format**: A valid false certificate is a Lean proof that instantiates a specific `Magma (Fin n)` with the found table, then calls `decideFin!` to let Lean verify it exhaustively.

### 2b. True Proof Strategies

All of these are deterministic and require zero LLM calls.

**Direct substitution**: Check all mappings from h's variables to goal's variables. If h with specific substitutions produces exactly the goal equation, emit `exact h args` or `exact (h args).symm`.

**Singleton collapse**: If the hypothesis forces all elements to be equal (e.g., `x = y ◇ z` where x does not appear on the RHS), then every equation holds trivially. Emit a singleton proof.

**simp only [h]**: Let Lean's simplifier repeatedly apply the hypothesis as a rewrite rule. Works surprisingly often for equations where h directly rewrites the goal's LHS into its RHS.

**Calc-chain BFS**: Build a graph where nodes are normalized expression strings and edges are h-instantiations. BFS from goal-LHS to goal-RHS. If a path is found, emit a `calc` chain.

**Constancy lemmas**: Derive `have hconst : ...` statements from free variables in h. Use these to bridge the gap between h's RHS structure and the goal's RHS structure.

**rw chains**: Try `rw [h args]` and `rw [← h args]` with the top-scoring variable substitutions.

### 2c. LLM Integration

The LLM is only called when all deterministic methods fail. The prompt must be highly structured because the model has no access to the problem context beyond what you provide.

**Key prompt elements**:
- The hypothesis and goal equations.
- Constancy analysis (which variables are free, what lemmas they yield).
- BFS near-miss results (if BFS got close but not all the way).
- Concrete h-instantiations (showing what h produces with specific arguments).
- The MATCH-COLLAPSE recipe.
- Previous judge errors (for retry rounds).

**Self-reflection loop**: When the judge rejects a proof, the error message contains structured information (type mismatch, expected vs got, unsolved goals). Parse this and include it in the next LLM prompt. The opnorm solver does basic error classification; we can do better by extracting the exact Lean goal state.

### 2d. Marathon-Specific Logic

**Triage**: Estimate difficulty before solving. Simple heuristics: equation size (number of operators), number of variables, whether the LHS is a single variable, whether there are free variables.

**Budget allocation**: Track remaining wall-clock and tokens. Allocate more time to problems that are almost solved (e.g., counterexample search found a table that satisfies Eq1 but the check for Eq2 violation was inconclusive).

**Few-shot cache**: When a proof is accepted, record the equation structure and the successful proof. For later problems with similar structure, prepend the cached proof as a few-shot example.

## Lean Code Generation

All generated Lean code follows these templates:

### False Certificate
```python
def make_false_code(n, table):
    table_str = json.dumps(table)
    return (
        "import JudgeProblem\n"
        "import JudgeDecide.DecideBang\n"
        "import JudgeFinOp.MemoFinOp\n"
        "open MemoFinOp\n\n"
        "def submission : Goal := by\n"
        f"  let m : Magma (Fin {n}) := {{\n"
        f"    op := finOpTable \"{table_str}\"\n"
        f"  }}\n"
        f"  refine ⟨Fin {n}, m, ?_⟩\n"
        f"  decideFin!\n"
    )
```

### True Certificate
```python
def make_true_code(proof_body):
    return (
        "import JudgeProblem\n\n"
        "def submission : Goal := by\n"
        "  intro G _ h\n"
        f"  {proof_body}\n"
    )
```

## Size Budget

The 500 KB limit is generous. The opnorm solver is 188 KB. We have room for:
- ~200 KB of solver logic
- ~100 KB of embedded lookup tables (known counterexamples, common proof patterns)
- ~100 KB of prompt text
- ~100 KB of buffer

## Dependencies

The solver runs in a sandboxed environment with:
- Python 3.8+ standard library
- `sympy` 1.13.3 (optional, for symbolic algebra)
- No numpy, z3, networkx, or other packages

All heavy computation must be pure Python or embedded in the solver itself.
