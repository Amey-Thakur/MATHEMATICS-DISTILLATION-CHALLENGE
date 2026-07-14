# Stage 1: Knowledge Distillation

This directory contains the preserved, untouched work from Stage 1 of the SAIR Mathematics Distillation Challenge.

## Context
Stage 1 was focused on extracting human-readable heuristics, prompt engineering, and producing concise cheatsheets. The overarching goal was to distill complex mathematical theories (specifically regarding magmas and equational theories) into formats that language models could effectively reason over without formal proof generation.

## Directory Layout
*   **`prompts/`**: Contains the `complete_prompt.template` and other prompt engineering artifacts used to query models.
*   **`cheatsheets/`**: Contains the distilled knowledge files, primarily `magma_cheatsheet.md`, optimized for token limits.
*   **`analysis/`**: Contains deep technical audits of the Stage 1 problem subsets and the underlying magma theories (`research.md`, `problem_analysis.md`).
*   **`scripts/`**: Python tools (`profile_datasets.py`, `process_runs.py`) used for profiling the data and mining model performance metrics.
*   **`sources/`**: Contains raw source data, including the initial ETP (Equational Theories Project) repository clones and SAIR subsets.

*Note: No files in this directory should be deleted, as they represent the foundational historical context of the project.*
