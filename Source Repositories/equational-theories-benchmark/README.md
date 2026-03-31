---
configs:
- config_name: benchmarks
  data_files:
  - split: train
    path: data/benchmarks.jsonl
- config_name: runs
  data_files:
  - split: train
    path: data/runs.jsonl
- config_name: cells
  data_files:
  - split: train
    path: data/cells.jsonl
- config_name: leaderboard
  data_files:
  - split: train
    path: data/leaderboard.jsonl
- config_name: models
  data_files:
  - split: train
    path: data/models.csv
- config_name: prompt_templates
  data_files:
  - split: train
    path: data/prompt_templates.jsonl
---

# Equational Theories Benchmark

This release packages four `common_25` benchmarks for Stage 1 of the Mathematics Distillation Challenge: Equational Theories.

Competition page:

- [https://competition.sair.foundation/competitions/mathematics-distillation-challenge-equational-theories-stage1](https://competition.sair.foundation/competitions/mathematics-distillation-challenge-equational-theories-stage1)

Playground:

- [https://playground.sair.foundation/playground/mathematics-distillation-challenge-equational-theories-stage1](https://playground.sair.foundation/playground/mathematics-distillation-challenge-equational-theories-stage1)

Problem dataset:

- [SAIRfoundation/equational-theories-selected-problems](https://huggingface.co/datasets/SAIRfoundation/equational-theories-selected-problems)

Included benchmark settings:

- `hard_200_common_25_low_reason`
- `hard_200_common_25_default_reason`
- `normal_200_common_25_low_reason`
- `normal_200_common_25_default_reason`

Common structure across the four settings:

- problems: 200 selected problems per benchmark
- models: 25 shared models in every benchmark
- repeats: 3 runs per model/problem pair
- prompt: `prompts/evaluation.jinja2`
- cheatsheets: none
- problem indexing: 1-based within each subset (`hard_0001`..`hard_0200`, `normal_0001`..`normal_0200`)

The task is equational implication over magmas: given Equation 1 and Equation 2, determine whether Equation 1 implies Equation 2.

## Files

- `data/benchmarks.jsonl`: one row per benchmark setting
- `data/runs.jsonl`: one row per model/problem/repeat run
- `data/cells.jsonl`: one row per model/problem cell, aggregating the three repeats
- `data/leaderboard.jsonl`: one row per model per benchmark with aggregate metrics
- `data/models.csv`: model registry for the shared `common_25` model set
- `data/prompt_templates.jsonl`: benchmark prompt metadata
- `prompts/evaluation.jinja2`: the evaluation prompt template used for every run in this release

## Benchmarks

- `hard_200_common_25_low_reason`: subset `hard`, reasoning `low_or_none`, temperature `low`, models `25`, repeats `3`
- `hard_200_common_25_default_reason`: subset `hard`, reasoning `default`, temperature `default`, models `25`, repeats `3`
- `normal_200_common_25_low_reason`: subset `normal`, reasoning `low_or_none`, temperature `low`, models `25`, repeats `3`
- `normal_200_common_25_default_reason`: subset `normal`, reasoning `default`, temperature `default`, models `25`, repeats `3`

## Configs

### `benchmarks`

One row per benchmark setting. This table records the benchmark identifier, problem subset, model count, repeat count, prompt template, reasoning mode, temperature mode, and cheatsheet mode.

### `runs`

The source-of-truth table. Each row contains one model run on one problem at one repeat.

Key fields:

- `benchmark_id`: benchmark setting identifier
- `problem_source_dataset`: source Hugging Face dataset
- `problem_subset`: problem subset within the source dataset
- `problem_index`: 1-based problem index within the subset
- `problem_id`: stable problem identifier such as `hard_0001` or `normal_0001`
- `equation1`, `equation2`, `answer`: problem content and gold label
- `template_id`: prompt template identifier
- `reasoning_mode`, `temperature_mode`: evaluation setting metadata
- `model_id`: normalized model identifier
- `model_id_raw`: raw model identifier from the provider export
- `repeat_id`: repeat number
- `response`: raw model output
- `correct`: whether the run was judged correct
- `judge_reason`: parsed judgment summary
- `elapsed_seconds`, `cost_usd`, `prompt_tokens`, `completion_tokens`: runtime metadata when available

### `cells`

One row per model/problem pair, aggregating the three repeats.

Key fields:

- `repeat_correct`: correctness of the three repeats
- `correct_count`: number of correct repeats
- `all_correct`: whether all repeats were correct
- `majority_correct`: whether at least two repeats were correct
- `any_correct`: whether at least one repeat was correct
- `mean_elapsed_seconds`, `mean_cost_usd`, `mean_prompt_tokens`, `mean_completion_tokens`: per-cell averages
- `repeats`: compact per-repeat summaries

### `leaderboard`

One row per model per benchmark with aggregate benchmark metrics.

Key fields:

- `accuracy`: correct runs divided by all runs
- `f1_score`: strict F1. Unparsed TRUE-labeled runs count as false negatives; unparsed FALSE-labeled runs count as false positives.
- `parse_success_rate`: fraction of runs with a parseable verdict
- official verdict parsing uses `judge_reason` only; raw `response` text is not used as a fallback for leaderboard metrics
- `avg_cost_usd`: average reported cost per run, computed only over runs with non-null cost
- `avg_time_secs`: average runtime per run
- `tp`, `fp`, `fn`, `tn`: confusion-matrix counts under the same strict rule as `f1_score`
- `unparsed`: number of runs without a parseable verdict
- `repeat_consistency`: average, across problems, of the fraction of the three repeats that agree with the majority judged verdict label for that model/problem cell, treating `TRUE`, `FALSE`, and `UNPARSED` as separate categories

### `models`

Model registry for the 25 shared models used in all four `common_25` benchmarks.

### `prompt_templates`

Maps each benchmark identifier to the prompt template used for evaluation.

## Usage

```python
from datasets import load_dataset

benchmarks = load_dataset(
    "SAIRfoundation/equational-theories-benchmark",
    "benchmarks",
    split="train",
)

runs = load_dataset(
    "SAIRfoundation/equational-theories-benchmark",
    "runs",
    split="train",
)

cells = load_dataset(
    "SAIRfoundation/equational-theories-benchmark",
    "cells",
    split="train",
)

leaderboard = load_dataset(
    "SAIRfoundation/equational-theories-benchmark",
    "leaderboard",
    split="train",
)
```
