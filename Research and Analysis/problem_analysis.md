# Stage 1 Problem Subset Analysis: SAIR Challenge
**Prepared by**: Amey Thakur

This document audits the 1,669 public problems released for Stage 1 of the SAIR Mathematics Distillation Challenge.

## Dataset Composition

The problems are divided into four subsets based on pattern recognition and algebraic reasoning:

| Subset | Problems | Verdict Split (T/F) | Curation Type |
| :--- | :--- | :--- | :--- |
| **Normal** | 1000 | 500 / 500 | Programmatic |
| **Hard1** | 69 | 24 / 45 | Hybrid (Human + AI) |
| **Hard2** | 200 | 100 / 100 | Hybrid (Human + AI) |
| **Hard3** | 400 | 195 / 205 | Programmatic (Heuristic-based) |

---

## Complexity Factors by Category

### 1. The "Normal" Baseline
Normal problems focus on:
*   **Total Triviality**: $E_1$ forces a singleton magma (Equation 2).
*   **Simple Rewrites**: $E_2$ is a direct substitution of $E_1$.
*   **Constant Magmas**: Expressions like $x \circ y = z \circ (w \circ w)$ which force all elements to be identical.

### 2. The "Hard1/2" Intuition Traps
These subsets defeat simple LLM heuristics.
*   **The Projection Trap**: Equations like $x = y \circ (y \circ ((x \circ y) \circ x))$ appear to force $x=y$ but allow for counter-magmas.
*   **Deceptive Symmetry**: $E_1$ and $E_2$ may look like duals but contain variable swaps that invalidate the implication.

### 3. The "Hard3" Algebraic Edge Cases
Hard3 focuses on properties that are mathematically distinct but look similar:
*   **Fixed-Point Failure**: ID $x \circ x = x \circ y$ implies the result depends only on the first variable. However, it does not imply $(x \circ x) \circ (x \circ x) = x \circ x$. This allows for functional behavior that refutes associative-like targets.
*   **Left-Identity-Like Behavior**: Identities that behave like identities ($x \circ e = x$) but lack a unique $e$, leading to TRUE implications for nested structures.

---

## Sample Problem Deep Dives

### Sample `hard3_0007` (The "Intuition Breaker")
*   **Equation 1**: `x * x = x * y`
*   **Equation 2**: `x * (y * z) = (x * z) * w`
*   **Verdict**: **FALSE**
*   **Reasoning**: Equation 1 implies that for any $x$, the result is a constant $f(x)$. Thus, $E_1 \equiv x \circ y = f(x)$. Applying this to Equation 2:
    *   LHS: $x \circ (y \circ z) = f(x)$
    *   RHS: $(x \circ z) \circ w = f(x \circ z) = f(f(x))$
    *   The implication holds iff $f(x) = f(f(x))$ for all $x$. Since $E_1$ does not force $f$ to be idempotent, a counterexample exists.

---

## Granular Algebraic Study Results

### 1. Structural vs. Logical Complexity Profile

Analysis of all 1,669 Stage 1 problems reveals the nesting distribution:

| Subset | Avg Term Depth (Parentheses) | Avg Variable Breadth | Complexity Type |
| :--- | :--- | :--- | :--- |
| **Normal** | **2.57** | 3.79 | Syntactic Nesting |
| **Hard1** | 2.36 | 3.55 | Logical Edge Cases |
| **Hard2** | 2.54 | 3.67 | Manual Curation |
| **Hard3** | 2.44 | 3.48 | Heuristic Traps |

**Conclusion**: Logical difficulty does not correlate with term depth. "Hard" problems are syntactically simpler but logically denser, requiring multi-step transitive proofs rather than following deep parentheses.

---

## State-of-the-AI Benchmark Insights

Analysis of 100,000 model runs from the `equational-theories-benchmark` identifies "Identity Bottlenecks" where models consistently fail.

### Bottleneck Identities (High Failure Rates)

1.  **Identity 706 (`x = y * (y * ((x * y) * x))`)**:
    *   **Context**: Often paired with ID 4204. Models struggle to identify if this forces a projection or a hidden cycle.
    *   **Failure Mode**: Models incorrectly guess **TRUE** assuming total variable recovery.
2.  **Identity 1274 (`x = x * (((y * z) * w) * u)`)**:
    *   **Context**: A right-weighted identity that looks trivial but has very few transitive implications.
    *   **Failure Mode**: Hallucination of commutativity under long nesting.

### Cognitive Guardrails for Distillation
*   **The Idempotency Mirage**: If $E_1$ establishes a functional dependency on $x$, models guess that $x \circ x = x$ is TRUE. **Strategy**: Explicitly flag $x \circ x = x$ as false unless a direct 1-step derivation exists.
*   **Variable Breadth Trap**: Problems with more than 4 variables are often "Red Herrings" where only 2 variables are actually operational.
