"""
prefilter.py - Programmatic image quality and metadata pre-filter.

WHAT:  This module will hold deterministic OpenCV, NumPy, perceptual hash, and
       EXIF checks for blur, lighting, glare, resolution, decode health,
       duplicate images, and non-original-image signals.
WHY:   The design uses cheap reproducible measurements to add risk signals,
       short-circuit dead image sets, and reduce VLM input cost without moving
       semantic damage review out of the vision model.
STEPS: Stub for STEPS.md Phase 2; created in Phase 0 item 3.
IN:    Resolved local image paths and image IDs.
OUT:   Per-image measurements, deterministic risk flags, dedup results, and
       all-images-dead indicators in later phases.
"""
