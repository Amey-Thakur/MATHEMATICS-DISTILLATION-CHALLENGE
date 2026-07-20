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

Do not write the intro line for the goal variables; it is added
automatically. Begin directly with the proof steps.

Use only these tactics: exact, have, calc, rw, congr_arg, .symm, .trans.
Never use: sorry, admit, decide, simp, simpa, aesop, omega, linarith,
tauto, ring, norm_num. Never claim a non-trivial equation by rfl.

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
import random
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


def search_affine(eq1, eq2, max_n):
    """Affine magmas a ◇ b = (p·a + q·b + s) mod n. The space is only n³ per
    order, yet these linear models witness a large share of the known false
    implications, reaching orders far beyond exhaustive table search."""
    max_vars = max(len(eq1[0]), len(eq2[0]))
    for n in range(2, max_n + 1):
        if n ** max_vars > 300_000:
            break
        for p in range(n):
            for q in range(n):
                for s in range(n):
                    op = lambda a, b, p=p, q=q, s=s, n=n: (p * a + q * b + s) % n
                    if holds(eq1, n, op) and violated(eq2, n, op):
                        table = [[op(a, b) for b in range(n)] for a in range(n)]
                        return n, table
    return None, None


def search_random(eq1, eq2, n, deadline, samples):
    """Random tables on Fin n with a cheap reject: most tables die on the
    first hypothesis tuple checked, so millions of candidates are affordable."""
    randint = random.randint
    for _ in range(samples):
        if time.monotonic() > deadline:
            return None
        table = [[randint(0, n - 1) for _ in range(n)] for _ in range(n)]
        op = lambda a, b, t=table: t[a][b]
        if holds(eq1, n, op) and violated(eq2, n, op):
            return table
    return None


def find_counterexample(eq1, eq2, budget_s):
    deadline = time.monotonic() + budget_s
    for n in (2, 3):
        table = search_exhaustive(eq1, eq2, n)
        if table is not None:
            return n, table

    n, table = search_affine(eq1, eq2, max_n=8)
    if n is not None:
        return n, table

    if time.monotonic() < deadline:
        table = search_backtrack(eq1, eq2, 4, deadline)
        if table is not None:
            return 4, table

    for n in (5, 6):
        if time.monotonic() >= deadline:
            break
        table = search_random(eq1, eq2, n, deadline, samples=400_000)
        if table is not None:
            return n, table
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


# -- rewrite prover for true implications ----------------------------------
#
# Simulates Lean's rw tactic exactly: instantiating the hypothesis gives a
# closed equation, and rw replaces every occurrence of its left side in the
# goal. A breadth-first search over short chains of such rewrites (forward
# and backward) closes many true implications outright, and the found chain
# is emitted verbatim as `intro ...; rw [h a b, ← h c d, ...]`.

def parse_tree(s, variables):
    """One side of an equation as a tree: a variable name, or ('.', l, r)."""
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
        return (".", parse_tree(s[:split_at], variables),
                parse_tree(s[split_at + 1:], variables))
    if len(s) == 1 and s in variables:
        return s
    raise ValueError("cannot parse: " + repr(s))


def tree_equation(text):
    seen = set()
    order = []
    for v in re.findall(r"\b([a-z])\b", text):
        if v not in seen:
            seen.add(v)
            order.append(v)
    lhs, rhs = text.split("=", 1)
    return order, parse_tree(lhs, seen), parse_tree(rhs, seen)


def subterms(t):
    yield t
    if isinstance(t, tuple):
        yield from subterms(t[1])
        yield from subterms(t[2])


def match(pattern, term, sigma):
    """Bind pattern variables (h's variables) against a ground term."""
    if isinstance(pattern, str):
        if pattern in sigma:
            return sigma[pattern] == term
        sigma[pattern] = term
        return True
    if not isinstance(term, tuple):
        return False
    return match(pattern[1], term[1], sigma) and match(pattern[2], term[2], sigma)


def subst(pattern, sigma):
    if isinstance(pattern, str):
        return sigma[pattern]
    return (".", subst(pattern[1], sigma), subst(pattern[2], sigma))


def rewrite_all(t, frm, to):
    if t == frm:
        return to
    if isinstance(t, tuple):
        return (".", rewrite_all(t[1], frm, to), rewrite_all(t[2], frm, to))
    return t


def render(t):
    if isinstance(t, str):
        return t
    return f"({render(t[1])} {OP} {render(t[2])})"


def rewrite_prove(eq1_text, eq2_text, budget_s=45, max_depth=5, max_nodes=20000):
    """Search for a rw chain from the goal to closure. Returns a proof body
    or None. Two passes: a fast one filling free hypothesis variables with
    goal variables only, then, on the remaining budget, a wide one that also
    fills with compound goal subterms. The narrow pass keeps short chains
    cheap under tight budgets; the wide pass reaches the deeper chains."""
    deadline = time.monotonic() + budget_s
    body = _rewrite_search(eq1_text, eq2_text, deadline - budget_s * 0.55,
                           max_depth, max_nodes, compound_fills=False)
    if body is not None:
        return body
    if time.monotonic() < deadline:
        return _rewrite_search(eq1_text, eq2_text, deadline,
                               max_depth, max_nodes, compound_fills=True)
    return None


def _rewrite_search(eq1_text, eq2_text, deadline, max_depth, max_nodes,
                    compound_fills):
    h_vars, h_lhs, h_rhs = tree_equation(eq1_text)
    g_vars, g_lhs, g_rhs = tree_equation(eq2_text)

    def moves(goal):
        out = []
        fill_pool = list(g_vars)
        if compound_fills:
            for side in goal:
                for u in subterms(side):
                    if isinstance(u, tuple) and u not in fill_pool:
                        fill_pool.append(u)
            fill_pool = fill_pool[:10]

        for arrow, pat, rep in (("", h_lhs, h_rhs), ("← ", h_rhs, h_lhs)):
            pat_vars = {v for v in subterms(pat) if isinstance(v, str)}
            free = [v for v in h_vars if v not in pat_vars]
            if len(free) > 2:
                continue
            for side in goal:
                for u in subterms(side):
                    sigma = {}
                    if not match(pat, u, sigma):
                        continue
                    for fills in product(fill_pool, repeat=len(free)):
                        s2 = dict(sigma)
                        for v, name in zip(free, fills):
                            s2[v] = name
                        frm = subst(pat, s2)
                        to = subst(rep, s2)
                        if frm == to:
                            continue
                        new_goal = (rewrite_all(goal[0], frm, to),
                                    rewrite_all(goal[1], frm, to))
                        if new_goal != goal:
                            args = " ".join(render(s2[v]) for v in h_vars)
                            out.append((f"{arrow}h {args}", new_goal))
        return out

    start = (g_lhs, g_rhs)
    if start[0] == start[1]:
        return f"intro {' '.join(g_vars)}\nrfl" if g_vars else "rfl"

    frontier = [(start, [])]
    visited = {repr(start)}
    for _ in range(max_depth):
        next_frontier = []
        for goal, path in frontier:
            if time.monotonic() > deadline or len(visited) > max_nodes:
                return None
            for step, new_goal in moves(goal):
                key = repr(new_goal)
                if key in visited:
                    continue
                visited.add(key)
                new_path = path + [step]
                if new_goal[0] == new_goal[1]:
                    steps = ", ".join(new_path)
                    intro = f"intro {' '.join(g_vars)}\n" if g_vars else ""
                    return f"{intro}rw [{steps}]"
                next_frontier.append((new_goal, new_path))
        frontier = next_frontier
        if not frontier:
            return None
    return None


# -- deterministic solve shared by both tracks -----------------------------

def solve_deterministic(problem, budget_s):
    """Return (verdict, code) if a deterministic certificate is found, else
    None. The budget splits toward the counterexample hunt, since a found
    table is checked before it ships while a rewrite chain can still fail
    at elaboration."""
    eq1_text = normalize(problem["equation1"])
    eq2_text = normalize(problem["equation2"])
    eq1 = parse_equation(eq1_text)
    eq2 = parse_equation(eq2_text)

    n, table = find_counterexample(eq1, eq2, budget_s * 0.7)
    if n is not None:
        return "false", make_false_code(n, table)

    body = collapse_proof(eq1_text, eq2_text)
    if body is not None:
        return "true", make_true_code(body)

    try:
        body = rewrite_prove(eq1_text, eq2_text, budget_s=budget_s * 0.3)
    except Exception:
        body = None
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


# Tactics the proof policy rejects or the judge routinely bounces; a body
# containing one is discarded before it wastes a judge call.
BANNED_TACTICS = re.compile(
    r"\b(sorry|admit|simp|simpa|aesop|omega|decide|tauto|norm_num|ring|"
    r"nlinarith|linarith|native_decide)\b"
)


def clean_proof_body(body):
    if ":= by" in body:
        body = re.sub(r"^.*?:=\s*by\s*\n?", "", body, count=1, flags=re.DOTALL)
    body = re.sub(r"^\s*by\s+", "", body)
    body = re.sub(r"^\s*import\s+.*\n?", "", body, flags=re.MULTILINE)
    body = body.strip()
    if BANNED_TACTICS.search(body):
        return ""
    return body


def code_from_answer(answer, eq1, eq2):
    """Turn a parsed model answer into Lean code, or None if unusable. A
    model counterexample is only forwarded when it verifies locally, so a
    problem whose equations did not parse cannot submit a false verdict.
    For true proofs the goal intro is imposed here: models regularly forget
    it, and that single omission rejected otherwise plausible proofs."""
    if answer.get("verdict") == "true":
        proof = clean_proof_body(answer.get("proof", ""))
        if not proof:
            return None
        if eq2 is not None and eq2[0]:
            proof = re.sub(r"^\s*intro[s]?\b[^\n]*\n?", "", proof, count=1)
            proof = f"intro {' '.join(eq2[0])}\n" + proof
        return make_true_code(proof)
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
            det = solve_deterministic(problem, budget_s=420)
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
    # Bounded model loop: eight rounds is where returns flatten, and a clean
    # exit beats grinding into the wall-clock kill. If the model flounders
    # for three rounds, one deeper rewrite search often ends the argument
    # deterministically before more tokens burn.
    for rnd in range(8):
        if rnd == 3 and eq1 is not None:
            try:
                body = rewrite_prove(problem["equation1"], problem["equation2"],
                                     budget_s=150, max_depth=7, max_nodes=80000)
            except Exception:
                body = None
            if body is not None:
                send_message({"call": "judge", "verdict": "true",
                              "code": make_true_code(body)})
                if read_message().get("status") == "accepted":
                    return
        send_message({"call": "llm", "context": {"round": str(rnd), "analysis": analysis}})
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
