# SAIR Mathematics Distillation Challenge: Equational Theories

**Prepared by**: Amey Thakur

This document details the SAIR foundation challenge for distilling magma equational reasoning. The goal is to improve LLM performance on formal equational implication tasks using human-readable cheatsheets.

## Research Organizers

Damek Davis (University of Pennsylvania)

Terence Tao (UCLA, SAIR Foundation)

SAIR Foundation

## Core Objective: Stage 1

The task requires determining whether a primary equation (Equation 1) implies a secondary equation (Equation 2) given a set of magma axioms.

### Example Case

Equation 4: x = x * y

Equation 3: x = x * x

Result: Equation 4 implies Equation 3 is True.

### Submission Requirements

Participants submit a prompt template and a cheatsheet. The prompt must include placeholders for { equation1 } and { equation2 }. The model must return a True or False response.

### Technical Constraints

Maximum Cheatsheet Size: 10 KB

Target Inference Cost: Less than 0.01 USD per problem

Maximum Solve Time: 10 minutes per problem

Environment: No-tools (no internet access or external code execution)

## Key Milestones

| Milestone | Date |
| :--- | :--- |
| Competition Commencement | March 14, 2026 |
| Stage 1 Submission Deadline | April 20, 2026 (23:59 AoE) |
| Leaderboard Publication | April 30, 2026 |
| Stage 2 Commencement | May 1, 2026 |

## Data Resources

Training and evaluation subsets are on Hugging Face:

Normal Difficulty (1,000 problems)

Hard Subset 1 (69 problems)

Hard Subset 2 (200 problems)

Hard Subset 3 (400 problems)

The evaluation set maintains a 50% distribution of True and False implications.

## Evaluation Infrastructure

Models utilized for benchmarking include:

OpenAI OSS Models

Llama Series

Gemini Flash Models

The final model selection will be finalized by April 10, 2026.

## Stage 2 Preview

The top 1,000 teams will advance to Stage 2. This phase involves increased difficulty and may require counterexamples, Lean proofs, or confidence probabilities.

## Primary Documentation Links

Zulip Community: https://zulip.sair.foundation/

Equational Theories Project: https://github.com/teorth/equational_theories

Standard Equation List: equations.txt (4,694 laws)
