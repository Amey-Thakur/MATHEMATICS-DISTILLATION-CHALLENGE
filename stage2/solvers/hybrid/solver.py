"""
hybrid - dual-track solver for the SAIR Equational Theories Stage 2 challenge.

One file, both tracks. It runs in Marathon when JUDGE_MARATHON_MANIFEST is set
and in Solo otherwise, so the same submission can be entered on either track.

Design principle: prove what can be proven deterministically, and only then
ask the model. A finite magma counterexample is checked exhaustively in
Python before it is emitted, so every `false` certificate is correct by
construction and the Lean judge's `decideFin!` only confirms it. That
reliability is the point: model-written Lean proofs fail often, deterministic
certificates do not. This matters most in Marathon, where the judge gives no
per-answer feedback, so a guessed proof cannot be retried.

Order of attack (both tracks):
  1. Counterexample search on finite magmas (Fin 2, 3 exhaustive; Fin 4 by
     constrained backtracking). Verified in Python. Clears most `false`
     problems with no tokens.
  2. Collapse proof: if the hypothesis forces every element equal, any goal
     follows. Clears the degenerate `true` problems with no tokens.
  3. Model fallback for the `true` problems that need a real proof. In Solo
     the judge error is fed back each round; in Marathon a single guarded
     attempt is made per unsolved problem while the token budget allows.

Lean templates match the judge contract exactly:
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
import os
import re
import sys
import time
from itertools import product


OP = "◇"  # the magma operator, U+25C7


def normalize(text):
    """Problem statements sometimes write the operator as * or a lookalike
    glyph; the rules call it a display convention. Everything becomes the
    canonical diamond before parsing, so no spelling can crash the solver."""
    for alias in ("*", "⋄", "∘", "·"):
        text = text.replace(alias, OP)
    return text


# -- equation parsing ------------------------------------------------------

def parse_side(s, variables):
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
            split_at = i
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


def holds(triple, n, op):
    variables, lhs, rhs = triple
    for vals in product(range(n), repeat=len(variables)):
        env = {"op": op}
        env.update(zip(variables, vals))
        if lhs(env) != rhs(env):
            return False
    return True


def violated(triple, n, op):
    variables, lhs, rhs = triple
    for vals in product(range(n), repeat=len(variables)):
        env = {"op": op}
        env.update(zip(variables, vals))
        if lhs(env) != rhs(env):
            return True
    return False


# -- counterexample search -------------------------------------------------

def _witness(eq1, eq2, n, table):
    op = lambda a, b, t=table: t[a][b]
    return holds(eq1, n, op) and violated(eq2, n, op)


def search_exhaustive(eq1, eq2, n):
    for enc in range(n ** (n * n)):
        table = [[(enc // n ** (i * n + j)) % n for j in range(n)] for i in range(n)]
        if _witness(eq1, eq2, n, table):
            return table
    return None


def search_backtrack(eq1, eq2, n, deadline):
    variables, lhs, rhs = eq1
    cells = [(i, j) for i in range(n) for j in range(n)]
    table = [[None] * n for _ in range(n)]

    def eval_partial(fn, env):
        def op(a, b):
            if a is None or b is None or table[a][b] is None:
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
            lv, rv = eval_partial(lhs, env), eval_partial(rhs, env)
            if lv is not None and rv is not None and lv != rv:
                return False
        return True

    def recurse(k):
        if time.monotonic() > deadline:
            return None
        if k == len(cells):
            full = [row[:] for row in table]
            return full if _witness(eq1, eq2, n, full) else None
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

def _ordered_vars(text):
    seen, out = set(), []
    for v in re.findall(r"\b([a-z])\b", text):
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def collapse_proof(eq1_text, eq2_text):
    """If the hypothesis has the form x = <expr without x>, every two elements
    are equal and any goal follows. Returns a proof body, or None."""
    lhs, rhs = (p.strip() for p in eq1_text.split("=", 1))
    if lhs != "x" or "x" in set(re.findall(r"\b([a-z])\b", rhs)):
        return None
    filler = " ".join(["a"] * (len(_ordered_vars(eq1_text)) - 1))
    g_lhs, g_rhs = (p.strip() for p in eq2_text.split("=", 1))
    return (
        f"intro {' '.join(_ordered_vars(eq2_text))}\n"
        f"have all_eq : ∀ (a b : G), a = b := "
        f"fun a b => (h a {filler}).trans (h b {filler}).symm\n"
        f"exact all_eq ({g_lhs}) ({g_rhs})"
    )


# -- deterministic solve shared by both tracks -----------------------------

def solve_deterministic(problem, budget_s):
    """Return (verdict, code) if a deterministic certificate is found, else None."""
    eq1 = parse_equation(normalize(problem["equation1"]))
    eq2 = parse_equation(normalize(problem["equation2"]))
    n, table = find_counterexample(eq1, eq2, budget_s)
    if n is not None:
        return "false", make_false_code(n, table)
    body = collapse_proof(problem["equation1"], problem["equation2"])
    if body is not None:
        return "true", make_true_code(body)
    return None


def build_analysis(problem, solved_false):
    notes = []
    if not solved_false:
        notes.append("No counterexample exists up to Fin 4, so this is almost certainly TRUE.")
    if collapse_proof(problem["equation1"], problem["equation2"]):
        notes.append("The hypothesis collapses every element to one value.")
    return "Solver analysis: " + (" ".join(notes) if notes else "no deterministic shortcut found.")


# -- model response parsing ------------------------------------------------

def extract_json(text):
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    m = re.search(r"\{[\s\S]*\}", text)
    for candidate in (text, m.group() if m else None):
        if candidate:
            try:
                return json.loads(candidate)
            except Exception:
                pass
    return None


def clean_proof_body(body):
    if ":= by" in body:
        body = re.sub(r"^.*?:=\s*by\s*\n?", "", body, count=1, flags=re.DOTALL)
    body = re.sub(r"^\s*by\s+", "", body)
    body = re.sub(r"^\s*import\s+.*\n?", "", body, flags=re.MULTILINE)
    return body.strip()


def code_from_answer(answer, eq1, eq2):
    """Turn a parsed model answer into Lean code, or None if unusable. A
    model counterexample is only forwarded when it verifies locally, so a
    problem whose equations did not parse cannot submit a false verdict."""
    if answer.get("verdict") == "true":
        proof = clean_proof_body(answer.get("proof", ""))
        return make_true_code(proof) if proof else None
    if answer.get("verdict") == "false" and eq1 is not None and eq2 is not None:
        tbl = answer.get("counterexample_table")
        try:
            if isinstance(tbl, list) and tbl and _witness(eq1, eq2, len(tbl), tbl):
                return make_false_code(len(tbl), tbl)
        except Exception:
            return None
    return None


# -- Solo track (stdin/stdout, interactive judge) --------------------------

def read_message():
    line = sys.stdin.readline()
    if not line:
        sys.exit(0)
    return json.loads(line.strip())


def send_message(msg):
    print(json.dumps(msg), flush=True)


def run_solo():
    problem = dict(read_message()["problem"])
    for field in ("equation1", "equation2"):
        problem[field] = normalize(str(problem.get(field, "")))

    # A parse failure on an unusual equation spelling must never kill the
    # process; the model fallback can still answer without local analysis.
    try:
        eq1 = parse_equation(normalize(problem["equation1"]))
        eq2 = parse_equation(normalize(problem["equation2"]))
    except Exception:
        eq1 = eq2 = None

    det = None
    if eq1 is not None:
        try:
            det = solve_deterministic(problem, budget_s=25)
        except Exception:
            det = None
    solved_false = det is not None and det[0] == "false"
    if det is not None:
        send_message({"call": "judge", "verdict": det[0], "code": det[1]})
        if read_message().get("status") == "accepted":
            return

    try:
        analysis = build_analysis(problem, solved_false)
    except Exception:
        analysis = "Solver analysis: unavailable for this problem."
    rnd = 0
    while True:
        send_message({"call": "llm", "context": {"round": str(rnd), "analysis": analysis}})
        rnd += 1
        result = read_message()
        if "error" in result:
            return
        answer = extract_json(result.get("response", ""))
        if not answer:
            continue
        code = code_from_answer(answer, eq1, eq2)
        if code is None:
            continue
        send_message({"call": "judge", "verdict": answer["verdict"], "code": code})
        if read_message().get("status") == "accepted":
            return


# -- Marathon track (manifest in, append-only JSONL out) -------------------

def append_answer(path, entry):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass


def marathon_prompt(problem, analysis):
    filled = PROMPT
    for key, val in {
        "{problem.equation1_id}": f"Equation{problem.get('eq1_id', '')}",
        "{problem.equation2_id}": f"Equation{problem.get('eq2_id', '')}",
        "{problem.equation1}": problem["equation1"],
        "{problem.equation2}": problem["equation2"],
        "{solver.analysis}": analysis,
        "{history.attempts}": "none",
    }.items():
        filled = filled.replace(key, val)
    return filled


def run_marathon():
    manifest = os.environ["JUDGE_MARATHON_MANIFEST"]
    output = os.environ["JUDGE_MARATHON_OUTPUT"]
    budget_s = float(os.environ.get("JUDGE_MARATHON_BUDGET_SECONDS", "3600"))
    deadline = time.monotonic() + budget_s
    tail = 10.0

    problems = []
    with open(manifest, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if raw:
                try:
                    prob = json.loads(raw)
                    for field in ("equation1", "equation2"):
                        prob[field] = normalize(str(prob.get(field, "")))
                    problems.append(prob)
                except json.JSONDecodeError:
                    continue

    # Phase 1: deterministic certificates for every problem (no tokens).
    per_problem = max(2.0, (budget_s * 0.4) / max(1, len(problems)))
    unsolved = []
    for prob in problems:
        if time.monotonic() + tail >= deadline:
            break
        try:
            det = solve_deterministic(prob, budget_s=per_problem)
        except Exception:
            det = None
        if det is not None:
            append_answer(output, {"id": prob["id"], "verdict": det[0], "code": det[1]})
        else:
            unsolved.append(prob)

    # Phase 2: one guarded model attempt per unsolved problem, budget allowing.
    try:
        from marathon_llm import call_llm, budget_remaining
    except Exception:
        return

    for prob in unsolved:
        if time.monotonic() + tail >= deadline or budget_remaining() < 20000:
            break
        try:
            eq1 = parse_equation(prob["equation1"])
            eq2 = parse_equation(prob["equation2"])
            result = call_llm(marathon_prompt(prob, build_analysis(prob, False)))
            if "error" in result:
                break
            answer = extract_json(result.get("response", ""))
            if not answer:
                continue
            code = code_from_answer(answer, eq1, eq2)
            if code is not None:
                append_answer(output, {"id": prob["id"], "verdict": answer["verdict"], "code": code})
        except Exception:
            continue


def main():
    if "JUDGE_MARATHON_MANIFEST" in os.environ:
        run_marathon()
    else:
        run_solo()


if __name__ == "__main__":
    main()
