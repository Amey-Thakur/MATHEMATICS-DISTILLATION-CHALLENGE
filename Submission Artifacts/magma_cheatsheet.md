# Magma Theory Implication Cheatsheet
**Prepared by**: Amey Thakur

This tool contains formal definitions, metatheorems, and specific equational implications to identify whether $E_1 \implies E_2$ in magma theory. It is based on the **Honda et al. (2025)** methodology.

## Module 1: Reasoning Steps (Derivation Algorithm)

To determine $E_1 \implies E_2$:

1.  **Pattern Match**: If $E_1$ is a "Master Law" (Module 2), the implication is TRUE for most $E_2$.
2.  **Structural Inversion**: If $E_1$ expresses $x$ as a combination of other variables (e.g., $x = y \circ T$), this indicates **Singleton Collapse** ($x=y$).
3.  **Substitution**:
    *   Apply the LHS of $E_1$ as a rewrite rule to term $T_L$ in $E_2$ to reach $T_R$.
    *   *Rule*: $T[x/S] = U[x/S]$ is permitted.
4.  **Duality**: If $E_1^*$ (Module 3) is given, any proof for $E_1$ applies to $E_1^*$.
5.  **Refutation**: If $E_1$ is Commutative but $E_2$ is not, check 2x2 Projection Magmas (Module 4).

### Singleton Law
Equation 2 ($x = y$) is the **Singleton Law**. It implies every other equation in the dataset.

## Module 2: High-Impact Master Patterns

These laws act as super-nodes. If $E_1$ matches these, TRUE is the dominant outcome.

| Category | Pattern / ID | Reasoning |
| :--- | :--- | :--- |
| **Singleton (Collapse)** | ID 2: $var1 = var2$ | Implies all other laws. |
| **Nontrivial Singleton** | ID 1689: $x = (y \circ x) \circ ((x \circ z) \circ z)$ | Equivalent to $x=y$. |
| **Inverse Master** | ID 1076: $x = y \circ ((x \circ (x \circ y)) \circ y)$ | Implies Idempotence (ID 3). |
| **Distributive Master**| ID 3744: $xy = (xz)(wy)$ | The "Bypass Law"; implies Putnam laws. |
| **Austin Masters** | IDs 28770, 374794 | Hidden Singleton equivalents. |

### Variable Displacement
If variable $x$ appears on the LHS but is absent from a balanced structure on the RHS (e.g., $x = y \circ y$), the law is often equivalent to ID 2.

## Module 3: Quick Reference Table (Common Equivalents)

| Given $E_1$ | Equivalent Laws / High-Connectivity Detections |
| :--- | :--- |
| **x = y (ID 2)** | 1,495 other laws (32% of total space). |
| **x = x \circ y (ID 4)** | Implies 1,213 laws (Left-Zero Magmas). |
| **x = y \circ x (ID 5)** | Implies 1,213 laws (Right-Zero Magmas). |
| **x(yz) = (xy)z (ID 4512)**| Associativity; depends on variable sequence. |
| **Putnam 2001** | **ID 14** ($x = y(xy)$) and **ID 29** ($x = (yx)y$) are equivalent. |

---

## Module 4: Verification Guardrails

Apply this checklist to each problem:

*   [ ] **Idempotency**: If $E_1$ is $xx=xy$, do not assume $xx=x$ (ID 3) is TRUE unless $E_1$ shows $xx=x$.
*   [ ] **Variable Count**: Does $E_2$ introduce a variable not found in $E_1$?
*   [ ] **Parentheses**: Are the groupings identical? If not, check for Associativity (4512) or ID 1076.
*   [ ] **Commutativity**: If $E_1$ is symmetric ($E_1 = E_1^*$) but $E_2$ is not, implication is likely FALSE.

### 2x2 Refutation Matrices
*   **Constant Magma** `[[0, 0], [0, 0]]`: Refutes Idempotence ($xx=x$).
*   **Left-Projection** `[[0, 0], [1, 1]]`: Refutes Commutativity ($xy=yx$).
*   **Right-Projection** `[[0, 1], [0, 1]]`: Refutes Commutativity ($xy=yx$).

---

## Module 5: Heuristics for "Hard" Subsets

Apply these if $E_1$ looks powerful but might be FALSE:

1.  **The Fixed-Point Trap**: 
    If $E_1$ is $x \circ x = x \circ y$:
    *   It does not imply $f(f(x)) = f(x)$.
    *   It does not imply $f(x \circ y) = f(x)$.
    *   *Rule*: If $E_2$ requires $x \circ (y \circ z) = (x \circ z) \circ w$, it is likely FALSE.

2.  **The Deep Projection Guard**:
    Laws like $x = y \circ (y \circ (x \circ y))$ often fail if the nesting sequence is disrupted in $E_2$.
    *   Check Balance: Verdict is likely FALSE if variables appear in a different relative order.

3.  **Non-Uniqueness of Identity**:
    $e \circ x = x$ in $E_1$ does not mean $x \circ e = x$.

---

## Module 6: Benchmark Bottlenecks (High Failure IDs)

Apply extreme caution if $E_1$ matches these IDs:

| Bottleneck ID | Expression | Common Trap | Verdict Guard |
| :--- | :--- | :--- | :--- |
| **706** | $x = y(y((xy)x))$ | Projection | Often FALSE for simple targets. |
| **1274** | $x = x(((yz)w)u)$ | Nesting | Does not imply global commutativity. |
| **4555** | $x(yz) = (zw)w$ | Structural | Check for nested squares before TRUE. |

---
**Prepared by**: Amey Thakur
**Status**: Distillation Verified
