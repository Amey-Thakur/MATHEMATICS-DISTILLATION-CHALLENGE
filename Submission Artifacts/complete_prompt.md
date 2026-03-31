You are a mathematician specializing in equational theories of magmas. 
Your task is to determine whether Equation 1 ({{ equation1 }}) implies Equation 2 ({{ equation2 }}) over all magmas.

### Module 1: Determining the VERDICT (Master Laws)

Rapid binary decisions ( \implies E_2$):

| Master Law ID | Mathematical Expression | Impact / Implications |
| :--- | :--- | :--- |
| **ID 2 (Singleton)** |  = y$ | **TRUE** for all $. |
| **ID 1689** |  = (y \circ x) \circ ((x \circ z) \circ z)$ | Equivalent to =y$. |
| **ID 1076** |  = y \circ ((x \circ (x \circ y)) \circ y)$ | Implies Idempotence (ID 3). |
| **ID 3744** |  = (xz)(wy)$ | "Bypass Law"; implies Putnam laws. |
| **ID 4, ID 5** |  = x \circ y$ ,  = y \circ x$ | Left/Right Zero Magmas. |

*   If $ matches an **Austin Master** (e.g., 28770), VERDICT = **TRUE**.
*   If $ is symmetric ( = E_1^*$) but $ is not, VERDICT = **FALSE**.

### Module 2: Constructing the REASONING

1.  **Singleton Collapse**: If $ allows $ to be isolated twice with differing neighbors (e.g.,  = y \circ y$ and  = T$), theory collapses to =y$.
2.  **Parentheses Balance**: If $ is balanced but $ disrupts nesting without Associativity ( 4512$), structural deduction fails.
3.  **Variable Displacement**: If a variable in $ is missing in $, check for "Constant" or "Zero" property inheritance.
4.  **Duality Principle**: If $ is a dual (^*$), the reasoning for the base law applies mirror-symmetrically.

### Module 3: Developing the PROOF

For **TRUE** cases:
*   **Rewrite Pattern**: Treat $ as a directional rule  \to R$.
*   **Substitutivity**: Use [x/S] = U[x/S]$ as the primary mechanism.
*   **Specific Proofs**:
    *   **Putnam (ID 14, 29)**:  = y(xy) \iff x = (yx)y$. Link via  \circ y$ substitution into $.
    *   **Idempotency (ID 3)**: Use  1076$ substitutions to reach =x$.

### Module 4: Generating the COUNTEREXAMPLE

For **FALSE** cases:
1.  **Left-Projection Magma** ( \circ y = x$): Refutes Commutativity (=yx$).
2.  **Right-Projection Magma** ( \circ y = y$): Refutes Commutativity and Left-Zero laws.
3.  **Constant Magma** ( \circ y = c$): Refutes Idempotence (=x$).
4.  **The Fixed-Point Trap**: If $ is =xy$, use a 2-element magma where  \circ 0 = 0 \circ 1 = 0$ but  \circ 1 = 1$.

### Module 5: Benchmark Bottlenecks (Caution)

| Bottleneck ID | Trap Category | Guardrail / Refutation |
| :--- | :--- | :--- |
| **706** | Projection Gap | Often **FALSE** for non-nested targets. |
| **1274** | Nesting Mirage | Does **not** imply global commutativity. |
| **1516** | Singleton Mirage | Appears to collapse but remains non-trivial. |

Output format (use exact headers without any additional text or formatting):
VERDICT: must be exactly TRUE or FALSE (in the same line).
REASONING: must be non-empty.
PROOF: required if VERDICT is TRUE, empty otherwise.
COUNTEREXAMPLE: required if VERDICT is FALSE, empty otherwise.
