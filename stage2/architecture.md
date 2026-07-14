# Stage 2 Architecture Proposal

## 1. System Overview
The Stage 2 solver requires a highly efficient, deterministic, and budget-aware architecture. The goal is to evaluate an equational implication `Eq1 => Eq2` and produce either a Lean 4 proof or a finite magma counterexample.

## 2. Core Components

### 2.1 Python Solver Engine (The Orchestrator)
The central Python script responsible for handling inputs, parsing ASTs, and determining the execution path.
- **AST Parsing**: Converts the input string equations into workable Abstract Syntax Trees.
- **Decision Engine**: Decides whether to prioritize a counterexample search or a proof synthesis based on structural heuristics.

### 2.2 Counterexample Generator (Deterministic)
Since the vast majority of random implications are false, proving falsity via finite magmas is the most statistically advantageous path.
- **Implementation**: A highly optimized C++ or Rust binary called via Python subprocess or FFI.
- **Mechanism**: Brute-force or heuristically guided search for small finite magmas that satisfy `Eq1` but violate `Eq2`.
- **Output**: JSON or string formatted finite magma matrix.

### 2.3 Proof Synthesizer (LLM Integration)
When the deterministic generator fails to find a counterexample within a specific time bound, the system pivots to proof generation.
- **Prompt Pipeline**: Constructs a Lean-specific prompt containing the theorems and required proofs.
- **Model Interaction**: Calls high-tier reasoning models (e.g., Claude 3.5 Sonnet, GPT-4o) via a proxy layer.

### 2.4 Proxy Layer
A localized caching and request management server.
- **Budget Optimization**: Ensures duplicate proofs are not requested.
- **Rate Limiting**: Manages API throughput to prevent 429 errors.
- **Provider Abstraction**: Interacts seamlessly with OpenRouter or direct APIs.

### 2.5 Validation Harness
Every generated proof MUST be validated locally before submission.
- **Lean 4 Judge**: The LLM output is compiled and verified by the Lean 4 command-line tool.
- **Self-Reflection Loop**: If the judge throws an error, the error is parsed and fed back to the LLM for a correction attempt.

## 3. Execution Flow
1. Receive `Eq1` and `Eq2`.
2. Start Counterexample search (Time limit: X seconds).
3. If Counterexample found -> Return `False` + Matrix.
4. If Counterexample search times out -> Query LLM for Proof.
5. Compile LLM output via local Lean 4 Judge.
6. If Valid -> Return `True` + Proof Certificate.
7. If Invalid -> Append error, retry LLM query (Max N retries).
8. If Retries exhausted -> Fallback to random guess or empty submission to minimize penalty.
