# ==============================================================================
# File: verify_solver.py
# Description: Pre-submission verification for the hybrid solver. Runs the
#   solver against every bundled problem set and checks the things the Lean
#   judge would check, using only what can be checked without a Lean
#   toolchain: the embedded verdict table against the ground truth answers in
#   the marathon manifests, every emitted false certificate re-parsed from its
#   Lean source and re-verified exhaustively in Python, every emitted true
#   proof screened for banned tactics and structural faults, both wire
#   protocols driven end to end against mock judges, and the sandbox rules on
#   imports and writes.
# Usage: py verify_solver.py [limit_per_set]
# Tech Stack: Python 3.10+ standard library only
# ==============================================================================

from __future__ import annotations

import ast
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from itertools import product
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import solver as S

PROBLEMS = Path(r"C:/Users/archi/OneDrive/Desktop/Shreyas/equational-theories-lean-stage2"
                r"/examples/problems")
BANNED = re.compile(r"\b(sorry|admit|sorryAx|simp|simpa|aesop|omega|decide|"
                    r"tauto|ring|norm_num|linarith|native_decide|#eval|#reduce|"
                    r"run_tac|macro|elab|unsafe|implemented_by|extern|dbg_trace)\b")
FAILURES = []


def fail(kind, detail):
    FAILURES.append((kind, detail))
    print(f"    FAIL [{kind}] {detail}")


def load(name):
    text = (PROBLEMS / name).read_text(encoding="utf-8").strip()
    if name.endswith(".json"):
        data = json.loads(text)
        return data.get("problems", data) if isinstance(data, dict) else data
    return [json.loads(l) for l in text.splitlines() if l.strip()]


# -- certificate re-verification -------------------------------------------

def table_from_false_code(code):
    """Pull the magma table back out of the emitted Lean source."""
    m = re.search(r'finOpTable\s+"(\[\[.*?\]\])"', code, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def recheck_false(problem, code):
    """Independently confirm the certificate: hypothesis holds on the table,
    goal fails on it. Parsed fresh, not reusing the solver's own objects."""
    table = table_from_false_code(code)
    if table is None:
        return "no finOpTable in emitted code"
    n = len(table)
    if any(len(row) != n or any(not (0 <= v < n) for v in row) for row in table):
        return f"table not a closed {n}x{n} operation"
    eq1 = S.parse_equation(S.normalize(problem["equation1"]))
    eq2 = S.parse_equation(S.normalize(problem["equation2"]))
    op = lambda a, b: table[a][b]

    def check(eq, want_all):
        names, lhs, rhs = eq
        hits = 0
        for values in product(range(n), repeat=len(names)):
            env = dict(zip(names, values))
            env["op"] = op
            ok = lhs(env) == rhs(env)
            if want_all and not ok:
                return False
            if not want_all and not ok:
                hits += 1
        return True if want_all else hits > 0

    if not check(eq1, True):
        return "hypothesis does NOT hold on the emitted table"
    if not check(eq2, False):
        return "goal is NOT violated on the emitted table"
    return None


def screen_true(code):
    """Structural screen of a true proof: judge policy and shape."""
    body = code
    if BANNED.search(body):
        return "banned tactic present: " + BANNED.search(body).group(0)
    if body.count("(") != body.count(")"):
        return "unbalanced parentheses"
    if body.count("[") != body.count("]"):
        return "unbalanced brackets"
    if "def submission : Goal := by" not in body:
        return "missing the required submission declaration"
    if "intro G _ h" not in body:
        return "missing the contract intro line"
    return None


# -- protocol drivers -------------------------------------------------------

def run_solo(problem, accept_after=1, timeout=180):
    """Drive the solver as the Solo judge would: send the problem, answer
    judge calls, count what it emits. Returns (messages, rc)."""
    env = dict(os.environ)
    env.pop("JUDGE_MARATHON_MANIFEST", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.Popen([sys.executable, str(HERE / "solver.py")],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", env=env)
    msgs = []
    try:
        proc.stdin.write(json.dumps({"problem": problem}) + "\n")
        proc.stdin.flush()
        judged = 0
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            msg = json.loads(line)
            msgs.append(msg)
            if msg.get("call") == "judge":
                judged += 1
                status = "accepted" if judged >= accept_after else "rejected"
                reply = {"status": status}
                if status == "rejected":
                    reply["error"] = "mock rejection"
                proc.stdin.write(json.dumps(reply) + "\n")
                proc.stdin.flush()
                if status == "accepted":
                    break
            elif msg.get("call") == "llm":
                proc.stdin.write(json.dumps({"response": "not json"}) + "\n")
                proc.stdin.flush()
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
    return msgs, proc.returncode


def run_marathon(problems, budget=90):
    """Drive the Marathon path against a real manifest file."""
    with tempfile.TemporaryDirectory() as tmp:
        manifest = Path(tmp) / "manifest.jsonl"
        output = Path(tmp) / "answers.jsonl"
        manifest.write_text(
            "\n".join(json.dumps(p, ensure_ascii=False) for p in problems) + "\n",
            encoding="utf-8")
        env = dict(os.environ)
        env["JUDGE_MARATHON_MANIFEST"] = str(manifest)
        env["JUDGE_MARATHON_OUTPUT"] = str(output)
        env["JUDGE_MARATHON_BUDGET_SECONDS"] = str(budget)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        proc = subprocess.run([sys.executable, str(HERE / "solver.py")],
                              capture_output=True, text=True, encoding="utf-8",
                              env=env, timeout=budget + 120)
        rows = []
        if output.exists():
            for line in output.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        return rows, proc.returncode, proc.stderr[-400:]


# -- checks -----------------------------------------------------------------

def check_sandbox_compliance():
    print("\n[1] sandbox compliance")
    tree = ast.parse((HERE / "solver.py").read_text(encoding="utf-8"))
    # marathon_llm is supplied by the official Marathon pipeline, not a
    # third-party package, and is imported inside the Marathon branch only.
    allowed = {"json", "os", "random", "re", "sys", "time", "itertools",
               "zlib", "base64", "marathon_llm"}
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            used.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            used.add(node.module.split(".")[0])
    extra = used - allowed
    if extra:
        fail("sandbox", f"non-stdlib or unexpected imports: {sorted(extra)}")
    else:
        print(f"    imports fine: {sorted(used)}")
    top_level = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])
    if "marathon_llm" in top_level:
        fail("sandbox", "marathon_llm imported at module level, would break Solo")
    else:
        print("    marathon_llm guarded inside the Marathon branch")
    size = (HERE / "solver.py").stat().st_size
    if size > 512000:
        fail("sandbox", f"solver {size} bytes exceeds 512000")
    else:
        print(f"    size {size} bytes of 512000")


def check_verdict_truth():
    print("\n[2] verdict table against ground truth")
    total = agree = 0
    for name in ("marathon/normal_100.jsonl", "hard1.jsonl", "hard2.jsonl",
                 "hard3.jsonl", "normal.jsonl"):
        try:
            probs = load(name)
        except Exception:
            continue
        withans = [p for p in probs if isinstance(p.get("answer"), bool)]
        if not withans:
            continue
        good = 0
        for p in withans:
            v = S.etp_verdict(p)
            truth = p["answer"]
            total += 1
            if (v == 1 and truth) or (v in (2, 3) and not truth):
                good += 1
                agree += 1
            elif v == 0:
                pass
            else:
                fail("verdict", f"{name} eq{p.get('eq1_id')}->eq{p.get('eq2_id')} "
                                f"table={v} truth={truth}")
        print(f"    {name}: {good}/{len(withans)} agree")
    if total:
        print(f"    overall {agree}/{total} = {100*agree/total:.1f}%")


def check_certificates(limit):
    print("\n[3] emitted certificates re-verified")
    random.seed(11)
    checked_f = checked_t = 0
    for name in ("sample_20.json", "normal.jsonl", "hard1.jsonl",
                 "hard2.jsonl", "hard3.jsonl"):
        try:
            probs = load(name)
        except Exception:
            continue
        if len(probs) > limit:
            probs = random.sample(probs, limit)
        for p in probs:
            try:
                det = S.solve_deterministic(p, budget_s=10)
            except Exception as exc:
                fail("crash", f"{name} {p.get('eq1_id')}->{p.get('eq2_id')}: {exc!r}")
                continue
            if not det:
                continue
            verdict, code = det
            truth = p.get("answer")
            if isinstance(truth, bool):
                if verdict == "true" and not truth:
                    fail("wrong-verdict", f"claimed true, truth false: "
                                          f"eq{p.get('eq1_id')}->eq{p.get('eq2_id')}")
                if verdict == "false" and truth:
                    fail("wrong-verdict", f"claimed false, truth true: "
                                          f"eq{p.get('eq1_id')}->eq{p.get('eq2_id')}")
            if verdict == "false":
                checked_f += 1
                why = recheck_false(p, code)
                if why:
                    fail("false-cert", f"eq{p.get('eq1_id')}->eq{p.get('eq2_id')}: {why}")
            else:
                checked_t += 1
                why = screen_true(code)
                if why:
                    fail("true-proof", f"eq{p.get('eq1_id')}->eq{p.get('eq2_id')}: {why}")
    print(f"    re-verified {checked_f} false certificates, "
          f"screened {checked_t} true proofs")


def check_protocols():
    print("\n[4] wire protocols")
    probs = load("sample_20.json")
    false_p = next(p for p in probs if S.etp_verdict(p) in (2, 3))
    msgs, rc = run_solo(false_p, accept_after=1)
    if rc != 0:
        fail("solo", f"exit code {rc}")
    if not msgs or msgs[0].get("call") != "judge":
        fail("solo", f"first message was not a judge call: {msgs[:1]}")
    else:
        print(f"    solo: first call judge verdict={msgs[0].get('verdict')}, "
              f"clean exit")
    # rejection path must not hang or crash
    msgs2, rc2 = run_solo(false_p, accept_after=99, timeout=120)
    if rc2 != 0:
        fail("solo", f"rejection path exit code {rc2}")
    else:
        print(f"    solo rejection path: {len(msgs2)} messages, clean exit")

    man = load("marathon/normal_100.jsonl")[:12]
    rows, rc3, err = run_marathon(man, budget=90)
    if rc3 != 0:
        fail("marathon", f"exit code {rc3}: {err}")
    answered = [r for r in rows if r.get("verdict") in ("true", "false")]
    print(f"    marathon: {len(answered)}/{len(man)} answered, exit {rc3}")
    for r in answered:
        src = next((p for p in man if str(p.get("id")) == str(r.get("id"))), None)
        if src and isinstance(src.get("answer"), bool):
            claimed = r["verdict"] == "true"
            if claimed != src["answer"]:
                fail("marathon", f"{r.get('id')} claimed {r['verdict']} "
                                 f"truth {src['answer']}")
        if src and r["verdict"] == "false":
            why = recheck_false(src, r.get("code", ""))
            if why:
                fail("marathon-cert", f"{r.get('id')}: {why}")


def check_edge_cases():
    print("\n[5] edge cases")
    cases = [
        ("star operator", {"eq1_id": 2, "eq2_id": 3,
                           "equation1": "x = y", "equation2": "x = x * x"}),
        ("missing ids", {"equation1": "x = y", "equation2": "x = x \u25c7 x"}),
        ("garbage", {"eq1_id": 1, "eq2_id": 2,
                     "equation1": "!!! not an equation",
                     "equation2": "???"}),
        ("empty", {"eq1_id": 1, "eq2_id": 2, "equation1": "", "equation2": ""}),
        ("out of range ids", {"eq1_id": 999999, "eq2_id": 5,
                              "equation1": "x = y", "equation2": "x = x \u25c7 x"}),
    ]
    for label, prob in cases:
        try:
            S.etp_verdict(prob)
            S.build_analysis(prob, False)
            try:
                S.solve_deterministic(prob, budget_s=3)
            except Exception:
                pass  # parse failures are allowed to raise here, run_solo guards
            print(f"    {label}: no crash in analysis path")
        except Exception as exc:
            fail("edge", f"{label}: {exc!r}")
    msgs, rc = run_solo(cases[2][1], accept_after=1, timeout=90)
    if rc != 0:
        fail("edge", f"garbage problem exit code {rc}")
    else:
        print("    garbage problem through solo: clean exit")


def main(limit=25):
    print("=" * 66)
    print("hybrid solver pre-submission verification")
    print("=" * 66)
    check_sandbox_compliance()
    check_verdict_truth()
    check_certificates(limit)
    check_protocols()
    check_edge_cases()
    print("\n" + "=" * 66)
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} FAILURES")
        for kind, detail in FAILURES[:20]:
            print(f"  [{kind}] {detail}")
        return 1
    print("RESULT: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 25))
