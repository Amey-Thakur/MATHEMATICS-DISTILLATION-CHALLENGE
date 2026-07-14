# Stage 2 Research Report: SAIR Mathematics Distillation Challenge

## Executive Summary
Stage 2 of the SAIR Mathematics Distillation Challenge represents a massive leap in complexity. The ETP (Equational Theories Project) demands that participants not only classify implications as true or false but formally prove their assertions. This research report maps the technical landscape required for a top-tier leaderboard finish.

## 1. The Challenge Mechanics
### 1.1 Proof Certificates
When asserting `True` (an implication holds), the solver must produce a valid Lean 4 theorem. This theorem must compile without errors against the ETP Lean environment.
- **Difficulty**: High. LLMs are notoriously inconsistent with Lean 4 syntax due to the language's rapid evolution and lack of extensive training data compared to Python or C++.
- **Strategy**: Leverage few-shot prompting with retrieved examples of similar proofs. Implement a tight verification loop.

### 1.2 Finite Magma Witnesses
When asserting `False` (an implication does not hold), the solver must provide a finite magma counterexample. A magma is simply a set with a binary operation.
- **Difficulty**: Medium. Generating magmas is mathematically straightforward but computationally explosive.
- **Strategy**: Brute-force search is feasible for very small magmas (e.g., size 3 or 4). Highly optimized algorithms (like those found in Mace4 or custom Rust/C++ solvers) are essential.

## 2. The Evaluation Pipeline
### 2.1 The Judge
The competition utilizes a deterministic Lean 4 judge.
- The judge will instantiate the submitted Lean proof.
- If the proof fails to compile or proves the wrong theorem, the submission is penalized or fails.
- Therefore, a local replica of the judge is mandatory. **Never submit an unverified proof to the live server.**

### 2.2 Budgeting and Constraints
Participants often face compute or API budget constraints.
- LLM inference is expensive and slow.
- Deterministic searches are cheap (locally) and fast.
- The pipeline must favor deterministic search first.

## 3. Advanced Strategies
### 3.1 The "False" Bias
In random mathematical implications, the vast majority are false. A solver that only attempts to find counterexamples and defaults to "False" (if allowed) or "Unknown" can achieve a baseline score rapidly.

### 3.2 Error-Driven Synthesis (Self-Reflection)
Lean 4 provides highly detailed compiler errors.
- Extract the error message, the context, and the current goal state.
- Prompt the LLM: "Your previous proof failed with this error: [Error]. The current state is [State]. Fix the proof."
- This loop significantly increases the success rate of LLM-generated formal proofs.

## 4. Open Questions & Unknowns
- What is the maximum acceptable size for a finite magma submission?
- What are the exact timeout limits per equation pair on the live runner?
- Can we pre-compute a database of universal counterexamples that violate specific common equations?

## 5. Next Steps
1. Clone the official Stage 2 evaluation repository locally.
2. Build the C++/Rust magma searcher.
3. Establish the Python orchestrator logic.
