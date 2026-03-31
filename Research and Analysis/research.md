# Magma Implication & AI Reasoning Bottlenecks: Research Document
**Prepared by**: Amey Thakur

**Date**: March 31, 2026
**Subject**: SAIR Mathematics Distillation Challenge
**Focus**: Magma Equational Theories, Cheat-Sheet ICL, and Logical Transitivities

---

## Technical Summary

This document presents the mathematics and computational results of the Equational Theories Project for AI distillation. Analysis of 22 million implication pairs and audit of 100,000 model benchmark runs reveals the logical drivers and failure modes of LLMs in formal algebraic reasoning. Distillation requires a move from syntactic string-matching to topological pattern recognition, targeting "Master Laws" and guarding against "Fixed-Point fallacies."

---

## 1. Formal Infrastructure: Lean 4 & Magma Theory

The task requires determining implications within the category of **Magmas** $(M, \circ)$, where $\circ$ is a binary operation without assumed properties.

### 1.1 The MagmaLaw Structure
In the `equational_theories` repository, laws are defined as terms within a free magma. The `MagmaLaw.lean` file defines terms recursively:
*   **Variables**: Leaf nodes in the term tree.
*   **Operations**: Binary nodes representing the application of $\circ$.

### 1.2 The Deductive System
Formal implications ($E_1 \implies E_2$) are established through a deductive system governed by:
1.  **Reflexivity**: $T = T$.
2.  **Symmetry**: $T_1 = T_2 \implies T_2 = T_1$.
3.  **Transitivity**: $T_1 = T_2 \land T_2 = T_3 \implies T_1 = T_3$.
4.  **Congruence (Substitution)**: $a = b \land c = d \implies (a \circ c) = (b \circ d)$.
5.  **Instantiation**: Replacing variables with arbitrary terms consistently across the identity.

---

## 2. Methodology: Cheat-Sheet In-Context Learning (ICL)

Following the framework in **Honda et al. (2025)**, the distillation process compresses the transitive knowledge of millions of proofs into a 10 KB textual summary.

### 2.1 The Transitive Closure Engine
The Equational Theories Project uses an extraction pipeline (`extract_implications.lean`) that processes proven Lean theorems into a directed acyclic graph (DAG) of implications. This DAG is communicated to an LLM through **Cognitive Anchors**: identities that represent the core of high-density cliques.

---

## 3. Empirical Structural Analysis (The Depth Paradox)

Automated profiling of the 1,669 Stage 1 problems reveals a finding regarding algebraic complexity.

### 3.1 Categorical Complexity Metrics

| Subset | Avg Term Depth | Avg Variable Breadth | Total Problems | Complexity Factor |
| :--- | :--- | :--- | :--- | :--- |
| **Normal** | **2.57** | 3.79 | 1000 | Syntactic Nesting |
| **Hard1** | 2.36 | 3.55 | 69 | Logical Edge Cases |
| **Hard2** | 2.54 | 3.67 | 200 | Manual Curation |
| **Hard3** | 2.44 | 3.48 | 400 | Heuristic Traps |

### 3.2 Result: Logical vs. Syntactic Depth
Logical difficulty is inverse to syntactic depth. "Hard" problems use simpler strings to hide non-obvious algebraic traps, whereas "Normal" problems use deep parentheses to mask trivial identities. Consequently, string-depth heuristics are insufficient for high-performance reasoning.

---

## 4. Topological Identification: Master Laws & Cliques

### 4.1 The Singleton Clique (Atomic Collapse)
Approximately 32.1% of the 4,694 laws are logically equivalent to the constant law $x=y$ (ID 2).
*   **Recognition Heuristic**: If $E_1$ allows for variable displacement (where a variable $x$ on the LHS has no structural partner on the RHS, e.g., $x = (y \circ y) \circ z$), the magma typically collapses into a singleton.

### 4.2 High-Connectivity Master Laws
Identified super-nodes that provide $O(1)$ resolution for thousands of targets:
*   **ID 1689**: $x = (y \circ x) \circ ((x \circ z) \circ z)$ (Singleton trigger)
*   **ID 1076**: $x = y \circ ((x \circ (x \circ y)) \circ y)$ (Idempotence trigger)
*   **ID 3744**: $xy = (xz)(wy)$ (The Bypass Law / Distributivity trigger)
*   **ID 4512**: Associativity (Baseline for structural rearrangement)

---

## 5. AI Reasoning Bottlenecks: Performance Mining

Analysis of 100,000 model runs identifies specific fault lines where LLMs consistently fail.

### 5.1 The Fixed-Point Fallacy (Idempotency Mirage)
Models assume that functional dependencies (e.g., $x \circ x = x \circ y$) force global idempotency ($x \circ x = x$).
*   **Algebraic Refutation**: In a 2x2 magma where $00=01=0$ and $10=11=1$, the law $xx=xy$ holds, but $xx=x$ does not hold for all structures if commutativity is absent.

### 5.2 Specific Bottleneck Pairs
*   **ID 706** (`x = y * (y * ((x * y) * x))`): Mistakenly identified as a pure projection, leading to false TRUE verdicts.
*   **ID 1274** (`x = x * (((y * z) * w) * u)`): Triggers hallucinatory commutativity in LLMs due to right-weighted nesting.

---

## 6. Verification Pipeline: Z3 & Automated Provers

To validate implications locally, the project integrates SMT solvers:
*   **Z3/CVC5**: Used for rapid counter-model generation. If a solver finds a finite magma (e.g., 3x3 size) satisfying $E_1$ but violating $E_2$, the implication is FALSE.
*   **Vampire**: First-order theorem prover used to close gaps where human-provided Lean proofs are missing.

---

## 7. Conclusions for Distillation

A perfectly detailed distillation strategy must prioritize **Boundary Recognition**:
1.  **Implication Thresholding**: Use "Master Law" tables to instantly resolve high-connectivity identities.
2.  **Structural Audits**: Filter out implications that violate variable count or symmetry balance.
3.  **Refutation Guardrails**: Use explicit 2x2 counter-matrices to prevent the "Idempotency Mirage."

---
**Prepared by**: Amey Thakur
**Verification Status**: Empirical Data Confirmed (Stage 1 Benchmark)
