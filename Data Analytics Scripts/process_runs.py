import json
import os

runs_path = r"C:\Users\AMEY THAKUR\Downloads\SAIR\equational-theories-benchmark\data\runs.jsonl"

print("Analyzing Model Failures (Sampling first 100,000 runs)...")
print("-" * 50)

failures = []
processed = 0

if os.path.exists(runs_path):
    with open(runs_path, 'r', encoding='utf-8') as f:
        for line in f:
            processed += 1
            if processed > 100000: break
            data = json.loads(line)
            # Filter for GPT-4 family or Claude if available
            if not data.get('correct', True):
                problem_id = data.get('problem_id')
                model = data.get('model_id')
                failures.append((problem_id, model))

# Grouping failures
from collections import Counter
common_failures = Counter(failures).most_common(10)

print(f"Top 10 Bottleneck Problems (ID, Model):")
for (pid, model), count in common_failures:
    print(f"ID: {pid:<15} | Model: {model:<20} | Fails: {count}")
