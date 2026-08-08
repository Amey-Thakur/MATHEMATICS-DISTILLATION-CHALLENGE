# ==============================================================================
# File: playground_validate.py
# Description: Runs the current solver against a balanced sample from every
#   playground problem set through the official playground API, then reports
#   acceptance per set and per expected verdict. The playground provides no
#   language model, so the pass criterion is: every false problem accepted,
#   every deterministically provable true accepted, and no run finishing with
#   an error status. Credits are spent at about one tenth per problem, so the
#   sample size is kept deliberately small.
# Usage: py playground_validate.py [per_set]
# Tech Stack: Python 3.10+, curl via subprocess
# ==============================================================================

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CID = "mathematics-distillation-challenge-equational-theories-stage2"
BASE = f"https://api.sair.foundation/api/public/v1/competitions/{CID}/playground"
KEY = os.environ.get("SAIR_API_KEY", "")
SETS = ["normal", "hard1", "hard2", "hard3", "evaluation_normal",
        "evaluation_hard", "evaluation_extra_hard", "evaluation_order5"]


def api(ep, payload=None):
    cmd = ["curl", "-sL", "--max-time", "180",
           "-H", f"Authorization: Bearer {KEY}", BASE + ep]
    if payload is not None:
        cmd = ["curl", "-sL", "--max-time", "180", "-X", "POST",
               "-H", f"Authorization: Bearer {KEY}",
               "-H", "Content-Type: application/json",
               "--data-binary", "@-", BASE + ep]
        proc = subprocess.run(cmd, input=json.dumps(payload),
                              capture_output=True, text=True,
                              encoding="utf-8")
    else:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8")
    return json.loads(proc.stdout)


def main(per_set=3):
    random.seed(41)
    ids = []
    for ps in SETS:
        items = api(f"/problem-sets/{ps}?limit=1000").get("data", {}).get("items", [])
        false_ids = [i["id"] for i in items if "_false_" in i["id"]]
        true_ids = [i["id"] for i in items if "_true_" in i["id"]]
        pick = (random.sample(false_ids, min(per_set, len(false_ids))) +
                random.sample(true_ids, min(per_set, len(true_ids))))
        ids.extend(pick)
    print(f"validating {len(ids)} problems across {len(SETS)} sets")

    code = (HERE / "solver.py").read_text(encoding="utf-8")
    run = api("/runs", {"solverCode": code, "solverName": "validate",
                        "allowedModels": ["openai-gpt-oss-120b"],
                        "problemIds": ids})
    rid = run.get("data", {}).get("runId")
    print("run:", rid)
    if not rid:
        print(json.dumps(run)[:300])
        return 1

    for _ in range(60):
        status = api(f"/runs/{rid}").get("data", {}).get("status")
        if status in ("done", "completed", "failed", "cancelled"):
            break
        time.sleep(30)
    items = api(f"/runs/{rid}/results?limit=200").get("data", {}).get("items", [])
    verdicts = Counter()
    failures = []
    for it in sorted(items, key=lambda x: x["problemId"]):
        pid = it["problemId"]
        v = it.get("verdict")
        expected_false = "_false_" in pid
        ok = v in ("true", "false")
        verdicts[v] += 1
        line = (f"  {pid:40} {str(v):8} "
                f"{(it.get('elapsedMs') or 0)/1000:7.1f}s "
                f"{(it.get('errorSnippet') or '')[:45]}")
        print(line)
        if expected_false and v != "false":
            failures.append((pid, "false problem not accepted"))
        if v == "error":
            failures.append((pid, "error status"))
    print(f"\nverdicts: {dict(verdicts)}")
    print(f"FALSE-side failures or errors: {len(failures)}")
    for pid, why in failures:
        print(f"  FAIL {pid}: {why}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3))
