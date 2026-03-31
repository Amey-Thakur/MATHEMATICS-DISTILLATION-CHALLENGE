import json
import os
import re

def get_depth(s):
    # Simple heuristic: max nested parentheses
    max_d = 0
    curr_d = 0
    for char in s:
        if char == '(':
            curr_d += 1
            max_d = max(max_d, curr_d)
        elif char == ')':
            curr_d -= 1
    return max_d

def get_vars(s):
    # Find all lowercase single letters as variables
    return set(re.findall(r'\b[a-z]\b', s))

def profile_jsonl(filepath):
    depths = []
    var_counts = []
    total = 0
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line)
            e1 = data['equation1']
            e2 = data['equation2']
            depths.append(max(get_depth(e1), get_depth(e2)))
            var_counts.append(len(get_vars(e1).union(get_vars(e2))))
            total += 1
    
    avg_depth = sum(depths) / len(depths) if depths else 0
    avg_vars = sum(var_counts) / len(var_counts) if var_counts else 0
    return {"avg_depth": round(avg_depth, 2), "avg_vars": round(avg_vars, 2), "total": total}

base_path = r"C:\Users\AMEY THAKUR\Downloads\SAIR\equational-theories-selected-problems\data"
subsets = ["normal.jsonl", "hard1.jsonl", "hard2.jsonl", "hard3.jsonl"]

print("SAIR Dataset Complexity Profile:")
print("-" * 40)
for s in subsets:
    path = os.path.join(base_path, s)
    if os.path.exists(path):
        stats = profile_jsonl(path)
        print(f"{s:15} | Depth: {stats['avg_depth']:<5} | Vars: {stats['avg_vars']:<5} | Count: {stats['total']}")
