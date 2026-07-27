#!/usr/bin/env python3
"""Check a solver against the competition sandbox constraints.

The evaluation sandbox is python:3.12-slim with **no third-party packages and
no network**, a read-only filesystem, and a hard cap on the submitted file
size. A solver that imports anything outside the standard library does not
fail slowly or partially: it dies on import, before the first problem, and
every answer is lost.

Nothing in the repository caught that, so this script is the gate. It is
deliberately dependency-free and reads the source rather than importing it,
so checking a solver can never execute it.

Run from the repository root:

    python stage2/scripts/check_solver.py

Exits non-zero and names the offending solver if any gated solver breaks a
constraint.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Official limit on the submitted solver file, in bytes.
MAX_SOLVER_BYTES = 512_000

# Provided by the judge harness inside the sandbox, so it resolves at runtime
# despite not being installed or importable here.
JUDGE_PROVIDED = {"marathon_llm"}

# Solvers that are actually submitted. These gate the build.
SUBMITTED = ["stage2/solvers/hybrid/solver.py"]

# Superseded solvers, kept for reference. Both are LLM-led, were rejecting in
# the playground, and import sympy, which the sandbox cannot provide. They are
# reported rather than gated so the repository records why they are retired
# instead of silently carrying a solver that cannot start.
LEGACY = [
    "stage2/solvers/gemma_4_31b/solver.py",
    "stage2/solvers/gpt_oss_120b/solver.py",
]


def imported_modules(tree: ast.AST) -> set[str]:
    """Every top-level package name imported anywhere in the file.

    Walks the whole tree rather than module level only: an import inside a
    function still runs inside the sandbox, and a deferred third-party import
    fails at the moment it is reached rather than at startup, which is worse.
    """
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # A relative import has no module to resolve against here.
            if node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    return modules


def has_prompt(tree: ast.AST) -> bool:
    """True when the file declares a module-level PROMPT string.

    The Solo protocol fills placeholders in this string, so a solver without
    one cannot call the model.
    """
    for node in tree.body:  # type: ignore[attr-defined]
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "PROMPT":
                return True
    return False


def check(path: Path) -> list[str]:
    """Return a list of problems with this solver. Empty means compliant."""
    problems: list[str] = []

    if not path.exists():
        return [f"{path}: not found"]

    size = path.stat().st_size
    if size > MAX_SOLVER_BYTES:
        problems.append(f"{path}: {size} bytes exceeds the {MAX_SOLVER_BYTES} byte limit")

    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        return problems + [f"{path}: does not parse ({error})"]

    allowed = set(sys.stdlib_module_names) | JUDGE_PROVIDED
    for module in sorted(imported_modules(tree) - allowed):
        problems.append(
            f"{path}: imports '{module}', which is not in the standard library "
            f"and cannot be installed in the sandbox"
        )

    if not has_prompt(tree):
        problems.append(f"{path}: no module-level PROMPT string")

    return problems


def main() -> int:
    root = Path(__file__).resolve().parents[2]

    failures: list[str] = []
    for relative in SUBMITTED:
        path = root / relative
        problems = check(path)
        if problems:
            failures.extend(problems)
        else:
            print(f"ok      {relative} ({path.stat().st_size} bytes)")

    for relative in LEGACY:
        path = root / relative
        problems = check(path)
        status = "legacy  " if problems else "ok      "
        print(f"{status}{relative}" + (" (not gated)" if problems else ""))
        for problem in problems:
            print(f"          {problem}")

    if failures:
        print("\nFAIL: a submitted solver breaks a sandbox constraint.", file=sys.stderr)
        for problem in failures:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print("\nPASS: every submitted solver satisfies the sandbox constraints.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
