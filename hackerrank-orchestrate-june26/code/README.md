# Damage Claim Verification Pipeline

This directory contains the runnable solution for the HackerRank Orchestrate multi-modal evidence review task. It reads the provided CSV files, inspects local claim images, calls Claude vision when selected, validates the model output against the required schema, and writes `output.csv`.

## Setup

Install the pinned dependencies from the project root:

```bash
pip install -r hackerrank-orchestrate-june26/requirements.txt
```

Set the Claude key either as an environment variable or in `hackerrank-orchestrate-june26/.env`:

```bash
ANTHROPIC_API_KEY=...
```

The `.env` file is ignored by git. The code loads it with the standard library and then reads `ANTHROPIC_API_KEY` from `os.environ`; no secret is hardcoded or printed.

## Run

Final Sonnet run over all 44 test claims:

```bash
python3 hackerrank-orchestrate-june26/code/main.py --client claude
```

This writes:

```text
hackerrank-orchestrate-june26/output.csv
```

Useful alternatives:

```bash
python3 hackerrank-orchestrate-june26/code/main.py --client mock
python3 hackerrank-orchestrate-june26/code/main.py --client claude-opus-4-8
CLAIM_PIPELINE_CLIENT=claude python3 hackerrank-orchestrate-june26/code/main.py
ANTHROPIC_MODEL_ID=claude-opus-4-8 python3 hackerrank-orchestrate-june26/code/main.py --client claude
```

`--client mock` is deterministic and makes zero API calls. `--client claude` uses `ANTHROPIC_MODEL_ID` when set, otherwise the default final model `claude-sonnet-4-6`. Passing any other `--client` value treats it as an explicit Claude model ID.

## Design

The pipeline follows the design document's staged evidence review:

1. Load `claims.csv`, `user_history.csv`, and `evidence_requirements.csv`.
2. Resolve semicolon-separated image paths relative to `dataset/`.
3. Run deterministic OpenCV/Pillow/imagehash pre-filter checks for blur, low light, glare, resolution, decode failures, duplicates, and EXIF non-original signals.
4. Extract a text claim structure without language detection or translation.
5. Make one multi-image Claude call per claim when using the real client.
6. Aggregate per-image findings into claim-level fields.
7. Apply user-history risk context.
8. Clamp every output field to the allowed values and enforce consistency invariants.
9. Cache model responses by content hash plus prompt version.
10. Write the exact 14-column `output.csv`.

Images remain the primary source of truth. User history adds risk flags only; it does not override clear visual evidence. In-image text is treated as untrusted evidence and never as an instruction.

## Evaluation

Run the required sample evaluation:

```bash
python3 hackerrank-orchestrate-june26/code/evaluation/main.py
```

The evaluator scores all 20 labeled sample rows and compares `claude-sonnet-4-6` against `claude-opus-4-8` when `ANTHROPIC_API_KEY` is available. If no key is present, it uses deterministic mock fallback clients under the same configuration labels so the workflow remains runnable offline.

The generated report lives at:

```text
hackerrank-orchestrate-june26/code/evaluation/evaluation_report.md
```

It includes per-field accuracy, `claim_status` macro-F1, a confusion matrix, Jaccard scores for set fields, model call counts, image counts, approximate token and cost estimates, runtime, TPM/RPM notes, caching, batching, and retry strategy.

## Submission Check

Before submitting:

- `hackerrank-orchestrate-june26/output.csv` has one row per row in `dataset/claims.csv`.
- `hackerrank-orchestrate-june26/output.csv` has exactly the required 14 columns in the required order.
- `hackerrank-orchestrate-june26/code/evaluation/main.py`, `metrics.py`, and `evaluation_report.md` are included in the code zip.
