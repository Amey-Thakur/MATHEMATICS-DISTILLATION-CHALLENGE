"""
hybrid - Solo-track solver for the SAIR Equational Theories Stage 2 challenge.

Design principle: prove what can be proven deterministically, and only then
ask the model. A finite magma counterexample is checked exhaustively in
Python before it is emitted, so every `false` certificate this solver sends
is correct by construction and the Lean judge's `decideFin!` only has to
confirm it. That reliability is the whole point: model-written Lean proofs
fail often, deterministic certificates do not.

Order of attack:
  1. Counterexample search on finite magmas (Fin 2, 3 exhaustive; Fin 4 by
     constrained backtracking). Clears most `false` problems with no tokens.
  2. Collapse proof: if the hypothesis forces every element equal, any goal
     follows. Clears the degenerate `true` problems with no tokens.
  3. Model fallback with a structural prompt and judge-error feedback, for
     the `true` problems that need a real proof.

The Lean templates match the judge contract exactly:
  true  : Goal = forall (G : Type) [Magma G], EquationLHS G -> EquationRHS G
  false : Goal = exists (G : Type) (_ : Magma G), EquationLHS G and not EquationRHS G
"""

PROMPT = """You are a Lean 4 proof engineer working on magma equational implications.

Hypothesis h ({problem.equation1_id}): {problem.equation1}
Goal      ({problem.equation2_id}): {problem.equation2}

{solver.analysis}

Previous attempts and judge errors:
{history.attempts}

The magma operator is written as the character U+25C7. Never write it as *.
The proof body runs after `intro G _ h`, so `h` is the hypothesis, universally
quantified over its variables. Derive the goal from `h`.

Use only these tactics: intro, exact, have, calc, congr_arg, .symm, .trans.
Never use: sorry, admit, decide, simp, aesop, omega, linarith, tauto.

The MATCH then COLLAPSE method solves almost all of these:
  MATCH:   instantiate h with compound arguments so its shape lines up with
           the goal's outer structure.
  COLLAPSE: use that free variables in h can take any value to rewrite the
           leftover inner terms into what the goal needs.

Respond with ONLY JSON, no markdown:
{"verdict": "true", "proof": "<tactic body, no theorem statement>"}
or
{"verdict": "false", "counterexample_table": [[0,1],[1,0]]}
"""


import json
import re
import sys
import time
from itertools import product


# -- protocol --------------------------------------------------------------

def read_message():
    line = sys.stdin.readline()
    if not line:
        sys.exit(0)
    return json.loads(line.strip())


def send_message(msg):
    print(json.dumps(msg), flush=True)


def call_judge(verdict, code):
    send_message({"call": "judge", "verdict": verdict, "code": code})
    return read_message()


def call_llm(context):
    send_message({"call": "llm", "context": context})
    return read_message()


# -- equation parsing ------------------------------------------------------

OP = "◇"  # the magma operator, U+25C7


def parse_side(s, variables):
    """Turn one side of an equation into a function env -> value."""
    s = s.strip()
    while len(s) >= 2 and s[0] == "(" and s[-1] == ")":
        depth = 0
        wraps = True
        for i, c in enumerate(s):
            depth += (c == "(") - (c == ")")
            if depth == 0 and i < len(s) - 1:
                wraps = False
                break
        if wraps:
            s = s[1:-1].strip()
        else:
            break

    depth = 0
    split_at = -1
    for i, c in enumerate(s):
        depth += (c == "(") - (c == ")")
        if depth == 0 and c == OP:
            split_at = i  # last top-level operator, left associative
    if split_at >= 0:
        left = parse_side(s[:split_at], variables)
        right = parse_side(s[split_at + 1:], variables)
        return lambda env, l=left, r=right: env["op"](l(env), r(env))

    if len(s) == 1 and s in variables:
        return lambda env, v=s: env[v]
    raise ValueError("cannot parse: " + repr(s))


def parse_equation(text):
    seen, variables = set(), []
    for v in re.findall(r"\b([a-z])\b", text):
        if v not in seen:
            seen.add(v)
            variables.append(v)
    lhs, rhs = text.split("=", 1)
    return variables, parse_side(lhs, seen), parse_side(rhs, seen)


def holds(variables, lhs, rhs, n, op):
    for vals in product(range(n), repeat=len(variables)):
        env = {"op": op}
        env.update(zip(variables, vals))
        if lhs(env) != rhs(env):
            return False
    return True


def violated(variables, lhs, rhs, n, op):
    for vals in product(range(n), repeat=len(variables)):
        env = {"op": op}
        env.update(zip(variables, vals))
        if lhs(env) != rhs(env):
            return True
    return False


# -- counterexample search -------------------------------------------------

def _witness(eq1, eq2, n, table):
    op = lambda a, b, t=table: t[a][b]
    return holds(*eq1, n, op) and violated(*eq2, n, op)


def search_exhaustive(eq1, eq2, n):
    """Every operation table on Fin n. Only sane for n <= 3."""
    for enc in range(n ** (n * n)):
        table = [[(enc // n ** (i * n + j)) % n for j in range(n)] for i in range(n)]
        if _witness(eq1, eq2, n, table):
            return table
    return None


def search_backtrack(eq1, eq2, n, deadline):
    """Fill the n*n table cell by cell, pruning as soon as a fully assigned
    hypothesis instance is violated. Returns a table satisfying the
    hypothesis and violating the goal, or None."""
    variables, lhs, rhs = eq1
    cells = [(i, j) for i in range(n) for j in range(n)]
    table = [[None] * n for _ in range(n)]

    def defined(a, b):
        return table[a][b] is not None

    def eval_partial(fn, env):
        # returns value or None if the expression touches an undefined cell
        def op(a, b):
            if a is None or b is None or not defined(a, b):
                raise KeyError
            return table[a][b]
        env2 = dict(env)
        env2["op"] = op
        try:
            return fn(env2)
        except KeyError:
            return None

    def hyp_ok():
        for vals in product(range(n), repeat=len(variables)):
            env = dict(zip(variables, vals))
            lv = eval_partial(lhs, env)
            rv = eval_partial(rhs, env)
            if lv is not None and rv is not None and lv != rv:
                return False
        return True

    def recurse(k):
        if time.monotonic() > deadline:
            return None
        if k == len(cells):
            if _witness(eq1, eq2, n, [row[:] for row in table]):
                return [row[:] for row in table]
            return None
        i, j = cells[k]
        for v in range(n):
            table[i][j] = v
            if hyp_ok():
                got = recurse(k + 1)
                if got is not None:
                    return got
        table[i][j] = None
        return None

    return recurse(0)


def find_counterexample(eq1, eq2, budget_s):
    deadline = time.monotonic() + budget_s
    for n in (2, 3):
        table = search_exhaustive(eq1, eq2, n)
        if table is not None:
            return n, table
    if time.monotonic() < deadline:
        table = search_backtrack(eq1, eq2, 4, deadline)
        if table is not None:
            return 4, table
    return None, None


# -- Lean code generation (matches the judge contract) ---------------------

def make_false_code(n, table):
    return (
        "import JudgeProblem\n"
        "import JudgeDecide.DecideBang\n"
        "import JudgeFinOp.MemoFinOp\n"
        "open MemoFinOp\n\n"
        "def submission : Goal := by\n"
        f"  let m : Magma (Fin {n}) := {{\n"
        f"    op := finOpTable \"{json.dumps(table)}\"\n"
        "  }\n"
        f"  refine ⟨Fin {n}, m, ?_⟩\n"
        "  decideFin!\n"
    )


def make_true_code(proof_body):
    body = "\n".join("  " + l if l.strip() else "" for l in proof_body.strip().split("\n"))
    return "import JudgeProblem\n\ndef submission : Goal := by\n  intro G _ h\n" + body + "\n"


# -- deterministic collapse proof ------------------------------------------

def collapse_proof(eq1_text, eq2_text):
    """If the hypothesis has the form x = <expr in which x does not appear>,
    then every two elements are equal and any goal follows. Returns a proof
    body, or None when the pattern does not apply."""
    lhs, rhs = (p.strip() for p in eq1_text.split("=", 1))
    if lhs != "x":
        return None
    if "x" in set(re.findall(r"\b([a-z])\b", rhs)):
        return None

    eq1_vars = _ordered_vars(eq1_text)
    eq2_vars = _ordered_vars(eq2_text)
    filler = " ".join(["a"] * (len(eq1_vars) - 1))
    g_lhs, g_rhs = (p.strip() for p in eq2_text.split("=", 1))
    return (
        f"intro {' '.join(eq2_vars)}\n"
        f"have all_eq : ∀ (a b : G), a = b := "
        f"fun a b => (h a {filler}).trans (h b {filler}).symm\n"
        f"exact all_eq ({g_lhs}) ({g_rhs})"
    )


def _ordered_vars(text):
    seen, out = set(), []
    for v in re.findall(r"\b([a-z])\b", text):
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


# -- model response parsing ------------------------------------------------

def extract_json(text):
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    for candidate in (text, _first_brace(text)):
        if candidate:
            try:
                return json.loads(candidate)
            except Exception:
                pass
    return None


def _first_brace(text):
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group() if m else None


def clean_proof_body(body):
    if ":= by" in body:
        body = re.sub(r"^.*?:=\s*by\s*\n?", "", body, count=1, flags=re.DOTALL)
    body = re.sub(r"^\s*by\s+", "", body)
    body = re.sub(r"^\s*import\s+.*\n?", "", body, flags=re.MULTILINE)
    return body.strip()


# -- main ------------------------------------------------------------------

def build_analysis(eq1_text, eq2_text, no_ce):
    notes = []
    if no_ce:
        notes.append("No counterexample exists up to Fin 4, so the implication is almost certainly TRUE.")
    if collapse_proof(eq1_text, eq2_text):
        notes.append("The hypothesis collapses every element to one value; a one-line all_eq proof works.")
    return "Solver analysis: " + (" ".join(notes) if notes else "no deterministic shortcut found.")


def main():
    startup = read_message()
    problem = startup["problem"]
    eq1_text, eq2_text = problem["equation1"], problem["equation2"]
    eq1 = parse_equation(eq1_text)
    eq2 = parse_equation(eq2_text)

    # Stage 1: deterministic counterexample (false).
    n, table = find_counterexample(eq1, eq2, budget_s=25)
    if n is not None and call_judge("false", make_false_code(n, table)).get("status") == "accepted":
        return

    # Stage 2: deterministic collapse proof (true).
    body = collapse_proof(eq1_text, eq2_text)
    if body and call_judge("true", make_true_code(body)).get("status") == "accepted":
        return

    # Stage 3: model fallback with structural analysis and judge feedback.
    analysis = build_analysis(eq1_text, eq2_text, no_ce=(n is None))
    rnd = 0
    while True:
        result = call_llm({"round": str(rnd), "analysis": analysis})
        rnd += 1
        if "error" in result:
            return
        answer = extract_json(result.get("response", ""))
        if not answer or answer.get("verdict") not in ("true", "false"):
            continue
        if answer["verdict"] == "true":
            proof = clean_proof_body(answer.get("proof", ""))
            if not proof:
                continue
            code = make_true_code(proof)
        else:
            tbl = answer.get("counterexample_table")
            if not isinstance(tbl, list) or not tbl:
                continue
            # Only trust a model counterexample if it verifies in Python.
            if not _witness(eq1, eq2, len(tbl), tbl):
                continue
            code = make_false_code(len(tbl), tbl)
        if call_judge(answer["verdict"], code).get("status") == "accepted":
            return


if __name__ == "__main__":
    main()
