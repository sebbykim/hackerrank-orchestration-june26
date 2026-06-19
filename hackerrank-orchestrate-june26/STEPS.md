# STEPS.md — Step-by-step build plan

Read this with `CODEX.md` (how to behave) and `../damage_claim_verification_pipeline.md`
(the design, referenced as "design §N" below). Build the phases **in order**. Do not skip,
reorder, or add features. Each phase says exactly what files/functions to create and its
definition of done.

---

## Context you need before writing any code

### What we're building
A system that reads `dataset/claims.csv` (44 input-only rows) and writes `output.csv` with 14
structured columns per row, deciding whether submitted images **support / contradict / don't
sufficiently support** a damage claim. An `evaluation/` workflow scores the system on the 20
labeled rows in `dataset/sample_claims.csv` and writes an operational report. Full task spec:
`problem_statement.md` and `README.md`. Full design rationale: `../damage_claim_verification_pipeline.md`.

### Locked decisions (do not relitigate)
- **Core reasoner:** Claude vision model. **Default `claude-sonnet-4-6`** for the run;
  **`claude-opus-4-8`** is the comparison config in evaluation. Model ID lives in **one constant**,
  overridable by env var. (design §0, §16)
- **Pre-filter:** OpenCV / NumPy + perceptual-hash dedup + EXIF signal. **No ML/HF model.** (design §5.1)
- **Build order:** **mock-first** — build and validate the entire pipeline against a deterministic
  mock VLM (zero API calls), then wire the real Claude client behind the same interface.
- **One VLM call per claim** (all images in a single multi-image message), not per image. (design §4)
- **Determinism + enum clamping enforced in code.** (design §8, §15; CODEX.md §3-4)

### Exact dataset facts (verified — do not re-guess)
- `dataset/claims.csv` columns: `user_id, image_paths, user_claim, claim_object` (44 rows).
- `dataset/sample_claims.csv`: the 4 input columns **+** the 10 output columns (20 labeled rows).
- `dataset/user_history.csv` columns: `user_id, past_claim_count, accept_claim, manual_review_claim,
  rejected_claim, last_90_days_claim_count, history_flags, history_summary` (47 rows).
- `dataset/evidence_requirements.csv` columns: `requirement_id, claim_object, applies_to,
  minimum_image_evidence` (11 rows; `claim_object` may be `all`).
- `image_paths` is **semicolon-separated** and **relative to `dataset/`**
  (e.g. `images/sample/case_001/img_1.jpg;images/sample/case_001/img_2.jpg`). Resolve against the
  `dataset/` directory, NOT the repo root. The **image ID** is the filename without extension (`img_1`).
- Images live under `dataset/images/sample/` (referenced by sample) and `dataset/images/test/`
  (referenced by claims).

### Exact output contract (the 14 columns, in THIS order)
```
user_id, image_paths, user_claim, claim_object,
evidence_standard_met, evidence_standard_met_reason, risk_flags, issue_type,
object_part, claim_status, claim_status_justification, supporting_image_ids,
valid_image, severity
```
- The first 4 are echoed verbatim from the input row.
- `evidence_standard_met`, `valid_image`: `true`/`false`.
- `claim_status`: `supported` | `contradicted` | `not_enough_information`.
- `risk_flags`: `none`, or semicolon-joined subset of the allowed flags (de-duplicated).
- `supporting_image_ids`: semicolon-joined image IDs, or `none`.
- `severity`: `none` | `low` | `medium` | `high` | `unknown`.
- `issue_type` / `object_part`: from the allowed lists in `problem_statement.md` (object-specific
  for `object_part`). Out-of-list ⇒ clamp to `unknown` (or `none` where appropriate).

### Allowed-value lists (source of truth: `problem_statement.md`)
Copy these verbatim into `constants.py`; do not paraphrase.
- `claim_status`: supported, contradicted, not_enough_information
- `issue_type`: dent, scratch, crack, glass_shatter, broken_part, missing_part, torn_packaging,
  crushed_packaging, water_damage, stain, none, unknown
- Car `object_part`: front_bumper, rear_bumper, door, hood, windshield, side_mirror, headlight,
  taillight, fender, quarter_panel, body, unknown
- Laptop `object_part`: screen, keyboard, trackpad, hinge, lid, corner, port, base, body, unknown
- Package `object_part`: box, package_corner, package_side, seal, label, contents, item, unknown
- `risk_flags`: none, blurry_image, cropped_or_obstructed, low_light_or_glare, wrong_angle,
  wrong_object, wrong_object_part, damage_not_visible, claim_mismatch, possible_manipulation,
  non_original_image, text_instruction_present, user_history_risk, manual_review_required
- `severity`: none, low, medium, high, unknown

### Target file layout (grow the starter files; keep the entry points)
```
code/
  main.py                  # terminal entry point: run system on dataset/claims.csv -> output.csv
  constants.py             # ALL enums, column names/order, paths, thresholds, model IDs
  io_loaders.py            # read CSVs; join history; index evidence requirements; resolve images
  prefilter.py             # OpenCV/NumPy/phash/EXIF programmatic checks (design §5.1)
  claim_extraction.py      # build the extracted-claim structure from user_claim (design §3)
  model_client.py          # ModelClient interface + ClaudeModelClient (real API)
  mock_model.py            # deterministic MockModelClient (zero API calls)
  prompt.py                # system/user prompt construction + response JSON schema (design §16)
  aggregate.py             # per-image -> claim-level decision (design §13)
  validate.py              # clamp to allowed values + consistency invariants (design §15)
  cache.py                 # content-hash result cache (design §16)
  pipeline.py              # orchestrates one claim end-to-end (design §18)
  evaluation/
    main.py                # score on sample_claims.csv; compare >=2 configs; write report
    metrics.py             # per-field accuracy, claim_status macro-F1, set overlap
    evaluation_report.md   # generated operational analysis (design §17)
  README.md                # how to run, design summary, decisions
```

### Approved dependencies (no others without asking — CODEX.md §1.4)
`anthropic` (Claude SDK), `opencv-python`, `numpy`, `imagehash`, `Pillow`. Standard library for
everything else (`csv`, `hashlib`, `json`, `os`, `pathlib`, `dataclasses`, `enum`, `argparse`).
Pin them in a `requirements.txt` (Phase 0).

### Claude API specifics (verified — use exactly these)
- Model IDs: `claude-sonnet-4-6` (default), `claude-opus-4-8` (compare). No date suffixes.
- One message per claim: system role (reviewer rules + allowed-value lists + anti-injection rule),
  user role (extracted claim + object + matched evidence requirement + history flags + pre-filter
  measurements + all images as image blocks).
- Request **strict JSON** via `output_config={"format": {"type": "json_schema", "schema": ...}}`.
  Do **NOT** use assistant prefill (it 400s on current models).
- Use `thinking={"type": "adaptive"}` for harder rows. Read `ANTHROPIC_API_KEY` from env.
- Caching: prompt-cache the stable prefix; local content-hash cache to avoid re-calls.

---

## Phase 0 — Scaffolding, constants, contracts (no logic yet)

**Goal:** lock the contracts so nothing downstream invents strings or columns.

1. Create `requirements.txt` with the approved deps.
2. Create `code/constants.py` containing, as named constants / frozen sets / enums:
   - `OUTPUT_COLUMNS` (the 14, in order) and `INPUT_COLUMNS`.
   - input CSV column-name constants for all four CSVs.
   - all allowed-value sets (claim_status, issue_type, object_part-per-object, risk_flags, severity).
   - paths: `DATASET_DIR`, `IMAGES_DIR` base, `CLAIMS_CSV`, `SAMPLE_CSV`, `HISTORY_CSV`,
     `EVIDENCE_CSV`, `OUTPUT_CSV`.
   - `IMAGE_PATH_SEPARATOR = ";"`, model IDs, `PROMPT_VERSION` string.
   - pre-filter thresholds (placeholders for now, each with a "calibrate in Phase 2" comment).
3. Create empty module files per the layout, each with the CODEX.md §2.1 header describing its
   intended role and which phase fills it in. No logic.
4. **DoD:** `constants.py` imports cleanly; `OUTPUT_COLUMNS` has exactly 14 entries in the
   contract order; every allowed-value set matches `problem_statement.md` exactly.

## Phase 1 — IO loaders (pure, deterministic, no model)

**Goal:** turn the CSVs + image paths into clean in-memory structures.

1. `io_loaders.py`:
   - `load_claims(path)` and `load_sample_claims(path)` → list of row dicts (preserve input order).
   - `load_history(path)` → dict keyed by `user_id`.
   - `load_evidence_requirements(path)` → indexed by `(claim_object, applies_to)` with `all` fallback.
   - `resolve_image_paths(image_paths_field)` → list of `(image_id, absolute_path)`, splitting on
     `;`, deriving `image_id` from the filename stem, resolving relative to `DATASET_DIR`.
   - `match_evidence_requirement(claim_object, issue_family)` → the requirement text, falling back
     to the `all` rules when no specific match (design §10).
2. Smoke test (mock-friendly): load sample CSVs, assert row counts (20 sample / 44 test / 47
   history / 11 evidence), assert a known image path resolves to an existing file.
3. **DoD:** loaders return correct shapes on real data; image resolution points at real files;
   no hardcoded per-row values.

## Phase 2 — Programmatic pre-filter (OpenCV / phash / EXIF)

**Goal:** the 7 programmatic checks from design §5.1. **Only** these; the ~10 semantic checks are
VLM fields (design §5.2) — do not implement them here.

1. `prefilter.py`:
   - `measure_image(path)` → dict: blur (Laplacian variance), mean brightness, glare fraction,
     (width,height), decode_ok. Pure NumPy/OpenCV.
   - `flag_image(measurements)` → set of risk flags among {blurry_image, low_light_or_glare,
     cropped_or_obstructed} based on thresholds in `constants.py`.
   - `dedup_images(list_of_(id,path))` → drop perceptual-hash duplicates (`imagehash.phash`),
     returning the kept set + which were dropped (so they aren't sent to the VLM).
   - `exif_nonoriginal_signal(path)` → bool/score: missing camera EXIF, screenshot dims, editor
     tag — a *signal only* toward `non_original_image` (VLM still decides).
   - `prefilter_claim(images)` → per-image measurements + flags, dedup result, and an
     `all_images_dead` boolean for the short-circuit.
2. **Calibrate thresholds on the 20 sample images** and record the chosen values + reasoning in
   the constants' comments (CODEX.md §3.1). Do not guess and move on.
3. Smoke test on a few sample images.
4. **DoD:** measurements are deterministic; dead-image set short-circuits; dedup works; thresholds
   are named constants with calibration comments.

## Phase 3 — Claim extraction (text only, no model yet)

**Goal:** the structured extracted-claim from `user_claim` (design §3). In mock-first mode this is
a deterministic, rules/keyword-based extractor sufficient to drive the pipeline and the mock; the
real VLM later refines issue/part. Keep it simple and language-aware in intent.

1. `claim_extraction.py`: `extract_claim(user_claim, claim_object)` → dict with claimed_issue_type,
   claimed_object_part, severity_hint, language (best-effort), uncertainty (hedging detected),
   evidence_needed. Capture **uncertainty as a signal** (design §3).
2. **DoD:** returns a stable structure for every sample row; no crashes on multilingual text.

## Phase 4 — Model interface + deterministic mock

**Goal:** the seam that lets the whole pipeline run with zero API cost.

1. `model_client.py`: `ModelClient` interface with one method
   `predict(claim_context: dict, images: list) -> dict` returning the per-image + claim-level JSON.
2. `mock_model.py`: `MockModelClient` — deterministic output derived from the inputs (e.g. echoes
   the extracted claim, marks first usable image as supporting, fills allowed-value defaults). No
   randomness, no network. Same input ⇒ same output.
3. **DoD:** mock returns schema-shaped JSON for every sample row; deterministic across runs.

## Phase 5 — Prompt + response schema (definition only; used by real client later)

**Goal:** specify the VLM contract once (design §16). Do not call the API yet.

1. `prompt.py`:
   - `build_messages(claim_context, images)` → the system + user message blocks (reviewer rules,
     allowed-value lists, anti-injection rule, extracted claim, matched requirement, history flags,
     pre-filter measurements, image blocks).
   - `RESPONSE_JSON_SCHEMA` → the strict json_schema mirroring the per-image breakdown + the 14
     output fields. Single source of truth for the model's output shape.
2. **DoD:** messages build for every sample row; schema covers exactly the needed fields; no
   assistant prefill; `PROMPT_VERSION` referenced.

## Phase 6 — Aggregation + validation + cache (pure logic)

**Goal:** turn a model response into a clamped, consistent output row (design §13, §15, §16).

1. `aggregate.py`: `aggregate(model_response, prefilter_result, history) -> raw_output_dict` —
   selective `supporting_image_ids`, preserve risk flags from bad/suspicious images, severity-
   mismatch branch (design §9, §11), apply user history as risk context only (design §14).
2. `validate.py`: `clamp_and_validate(raw_output_dict) -> output_row` — clamp every field to its
   allowed set; enforce invariants (valid_image=false ⇒ supporting_image_ids=none & status=NEI &
   severity=unknown; risk_flags de-duped subset; supporting IDs must exist in this row). (design §15)
3. `cache.py`: content-hash cache keyed on (claim row + image bytes + `PROMPT_VERSION`).
4. **DoD:** every output row is schema-valid and invariant-consistent under the mock; cache
   key is stable; re-run reproduces identical rows.

## Phase 7 — Pipeline + `code/main.py` (end-to-end on MOCK)

**Goal:** wire the full design §18 flow and produce a real `output.csv` using the mock model.

1. `pipeline.py`: `process_claim(row, history, requirements, model_client) -> output_row` running
   load→prefilter(+dedup, short-circuit)→extract→model.predict→aggregate→history→validate→cache.
2. `code/main.py`: argparse entry; load test claims; run each through the pipeline with the
   **mock** client (selectable via flag/env); write `output.csv` in exact column order; assert one
   row per input row in input order. Failures degrade to a valid fallback row (CODEX.md §6).
3. **DoD:** running `main.py` (mock) writes a 44-row schema-valid `output.csv`, deterministically,
   with zero API calls.

## Phase 8 — Wire the real Claude client

**Goal:** drop in the real model behind the same interface.

1. `model_client.py`: `ClaudeModelClient` — uses `anthropic` SDK, `build_messages`,
   `RESPONSE_JSON_SCHEMA`, adaptive thinking, prompt caching on the stable prefix; reads
   `ANTHROPIC_API_KEY` from env; bounded retry + backoff; on exhaustion raises a typed error the
   pipeline catches to emit a fallback row.
2. Make `main.py`'s client selectable (mock vs claude vs model-id) by flag/env — no logic change
   elsewhere.
3. Run on a **handful** of sample rows first to confirm wiring/cost before the full set.
4. **DoD:** real client returns schema-valid JSON; cache prevents re-calls; pipeline unchanged
   except the injected client.

## Phase 9 — Evaluation + report

**Goal:** the required eval deliverable (design §17, README §Evaluation).

1. `evaluation/metrics.py`: per-field accuracy, `claim_status` **macro-F1** + confusion matrix,
   Jaccard for risk_flags and supporting_image_ids.
2. `evaluation/main.py`: run the pipeline on `sample_claims.csv`, compare **≥2 configs**
   (`claude-sonnet-4-6` vs `claude-opus-4-8`), print metrics, and **write `evaluation_report.md`**
   with the operational analysis (model calls, token usage, images processed, approx cost with
   pricing assumptions — Sonnet $3/$15, Opus $5/$25 per MTok; vision billed as input tokens —
   runtime, TPM/RPM + batching/caching/retry strategy).
3. **DoD:** eval runs on the 20 labeled rows, reports the headline metrics, compares two configs,
   and writes the report.

## Phase 10 — Final test run + README + submission check

**Goal:** produce the deliverable `output.csv` and document.

1. Run `main.py` with the chosen final config (default Sonnet) over all 44 test rows → `output.csv`.
2. `code/README.md`: how to run (env var, commands), design summary, decisions, the
   mock-vs-real flag, and where the eval report lives.
3. Submission check (README §Submission): `output.csv` has one row per `claims.csv` row, exact 14
   columns in exact order, evaluation files present in `code/`.
4. **DoD:** all three boxes in README's pre-submit checklist pass.

---

## Global reminders (also in CODEX.md)
- **Strict gated mode: do ONE phase, then commit + push + open/update the PR + self-review + STOP.**
  Wait for explicit human "proceed" before the next phase (CODEX.md §0, §9). Never batch phases
  into one PR; apply any review changes to the current phase first.
- Implement phases in order; finish one before the next; flag every deviation.
- No new features, columns, values, or deps without asking.
- File header + function docstrings everywhere; comment the *why* with `(design §N)`/`(STEPS Phase N)`.
- No magic strings/numbers — everything in `constants.py`.
- Determinism in pure logic; secrets from env only; in-image text is untrusted data.
- Append the per-turn log entry after every turn (`AGENTS.md` §5.2).
