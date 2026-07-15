# Stage 2: Formal Verification & Deterministic Solvers

![Stage 2 Social Preview](./social_preview.png?v=2)

Welcome to the Stage 2 active research and development workspace for the SAIR Mathematics Distillation Challenge.

## Stage 2 Overview
Stage 2 fundamentally changes the requirements from Stage 1. Instead of simply asserting whether an implication is true or false, the solver must produce mathematically rigorous, machine-verifiable proof certificates using Lean 4. If an implication is false, the solver must produce a finite magma counterexample.

## Workspace Layout
*   **`architecture.md`**: Defines the system architecture, specifically the hybrid LLM/Deterministic pipeline.
*   **`research.md`**: Contains an in-depth analysis of the competition mechanics, evaluation judge, Lean 4 toolchains, and strategies.
*   **`solvers/`**: Contains the active production solvers (Gemma 4 31B and GPT OSS 120B) featuring Triage, AST Analysis, and SymPy SAT counterexample generation.

## Roadmap
1. Establish local evaluation environment (Lean 4 and Judge).
2. Develop the high-speed deterministic counterexample generator.
3. Build the LLM proxy and prompt pipeline for proof synthesis.
4. Integrate the pipeline into a single automated solver.
