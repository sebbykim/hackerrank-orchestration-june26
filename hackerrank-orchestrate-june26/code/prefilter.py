"""
prefilter.py - Programmatic image quality and metadata pre-filter.

WHAT:  This module performs deterministic OpenCV, NumPy, perceptual hash, and
       EXIF checks for blur, lighting, glare, resolution, decode health,
       duplicate images, and non-original-image signals.
WHY:   The design uses cheap reproducible measurements to add risk signals,
       short-circuit dead image sets, and reduce VLM input cost without moving
       semantic damage review out of the vision model.
STEPS: Implements STEPS.md Phase 2 items 1-3.
IN:    Resolved local image paths and image IDs.
OUT:   Per-image measurements, deterministic risk flags, dedup results, and
       all-images-dead indicators.
"""

from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

import cv2
import imagehash
import numpy as np
from PIL import Image, UnidentifiedImageError

from constants import (
    COL_IMAGE_PATHS,
    EXIF_CAMERA_TAG_IDS,
    EXIF_EDITOR_SOFTWARE_MARKERS,
    EXIF_EDITOR_SOFTWARE_SIGNAL_SCORE,
    EXIF_MISSING_CAMERA_SIGNAL_SCORE,
    EXIF_NON_ORIGINAL_SIGNAL_SCORE_THRESHOLD,
    EXIF_REASON_EDITOR_SOFTWARE,
    EXIF_REASON_MISSING_CAMERA,
    EXIF_REASON_SCREENSHOT_DIMENSIONS,
    EXIF_SCREENSHOT_DIMENSION_SIGNAL_SCORE,
    EXIF_SCREENSHOT_LONG_EDGE_MIN,
    EXIF_SCREENSHOT_TALL_ASPECT_RATIO,
    EXIF_SCREENSHOT_WIDE_ASPECT_RATIO,
    EXIF_SOFTWARE_TAG_ID,
    PREFILTER_BLUR_LAPLACIAN_VAR_THRESHOLD,
    PREFILTER_DEAD_MEAN_BRIGHTNESS_THRESHOLD,
    PREFILTER_DEFAULT_IMAGE_DIMENSION,
    PREFILTER_DEFAULT_MEASUREMENT_VALUE,
    PREFILTER_DEFAULT_SIGNAL_SCORE,
    PREFILTER_DUPLICATE_TEST_SUFFIX,
    PREFILTER_GLARE_FRACTION_THRESHOLD,
    PREFILTER_GLARE_PIXEL_VALUE_THRESHOLD,
    PREFILTER_KEY_ALL_IMAGES_DEAD,
    PREFILTER_KEY_BLUR_LAPLACIAN_VAR,
    PREFILTER_KEY_DECODE_OK,
    PREFILTER_KEY_DEDUP,
    PREFILTER_KEY_DROPPED_DUPLICATES,
    PREFILTER_KEY_EDITOR_SOFTWARE,
    PREFILTER_KEY_EXIF,
    PREFILTER_KEY_FLAGS,
    PREFILTER_KEY_GLARE_FRACTION,
    PREFILTER_KEY_HEIGHT,
    PREFILTER_KEY_IMAGE_ID,
    PREFILTER_KEY_KEPT_IMAGE_IDS,
    PREFILTER_KEY_KEPT_IMAGES,
    PREFILTER_KEY_MEAN_BRIGHTNESS,
    PREFILTER_KEY_MISSING_CAMERA_EXIF,
    PREFILTER_KEY_NON_ORIGINAL_SIGNAL,
    PREFILTER_KEY_PATH,
    PREFILTER_KEY_PER_IMAGE,
    PREFILTER_KEY_SCREENSHOT_DIMENSIONS,
    PREFILTER_KEY_SIGNAL_REASONS,
    PREFILTER_KEY_SIGNAL_SCORE,
    PREFILTER_KEY_WIDTH,
    PREFILTER_MEAN_BRIGHTNESS_LOW_THRESHOLD,
    PREFILTER_MIN_IMAGE_HEIGHT,
    PREFILTER_MIN_IMAGE_WIDTH,
    PREFILTER_PHASH_DUPLICATE_DISTANCE_THRESHOLD,
    RISK_FLAG_BLURRY_IMAGE,
    RISK_FLAG_CROPPED_OR_OBSTRUCTED,
    RISK_FLAG_LOW_LIGHT_OR_GLARE,
    SAMPLE_CSV,
)
from io_loaders import load_sample_claims, resolve_image_paths


ImageRef = Tuple[str, Path]
Measurement = Dict[str, object]
ExifSignal = Dict[str, object]
DedupResult = Dict[str, object]
PrefilterResult = Dict[str, object]


def measure_image(path: Path) -> Measurement:
    """Measure deterministic pixel statistics for one local image.

    Args:
        path: Local image path to decode with OpenCV.

    Returns:
        A measurement dictionary with decode status, blur score, brightness,
        glare fraction, width, and height. Decode failures return safe default
        numeric fields so later phases can still emit a valid fallback row.
    """
    image_path = Path(path)
    image = cv2.imread(str(image_path))
    if image is None:
        return {
            PREFILTER_KEY_DECODE_OK: False,
            PREFILTER_KEY_BLUR_LAPLACIAN_VAR: PREFILTER_DEFAULT_MEASUREMENT_VALUE,
            PREFILTER_KEY_MEAN_BRIGHTNESS: PREFILTER_DEFAULT_MEASUREMENT_VALUE,
            PREFILTER_KEY_GLARE_FRACTION: PREFILTER_DEFAULT_MEASUREMENT_VALUE,
            PREFILTER_KEY_WIDTH: PREFILTER_DEFAULT_IMAGE_DIMENSION,
            PREFILTER_KEY_HEIGHT: PREFILTER_DEFAULT_IMAGE_DIMENSION,
        }

    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray_image.shape[:2]
    blur_score = float(cv2.Laplacian(gray_image, cv2.CV_64F).var())
    mean_brightness = float(np.mean(gray_image))
    glare_fraction = float(
        np.mean(gray_image >= PREFILTER_GLARE_PIXEL_VALUE_THRESHOLD)
    )
    return {
        PREFILTER_KEY_DECODE_OK: True,
        PREFILTER_KEY_BLUR_LAPLACIAN_VAR: blur_score,
        PREFILTER_KEY_MEAN_BRIGHTNESS: mean_brightness,
        PREFILTER_KEY_GLARE_FRACTION: glare_fraction,
        PREFILTER_KEY_WIDTH: int(width),
        PREFILTER_KEY_HEIGHT: int(height),
    }


def flag_image(measurements: Measurement) -> Set[str]:
    """Convert measured pixel statistics into deterministic quality risk flags.

    Args:
        measurements: Output from measure_image().

    Returns:
        A set containing only Phase 2 programmatic risk flags. Semantic flags
        such as wrong_object remain VLM responsibilities (design §5.2).
    """
    if not measurements[PREFILTER_KEY_DECODE_OK]:
        return set()

    flags: Set[str] = set()
    if (
        measurements[PREFILTER_KEY_BLUR_LAPLACIAN_VAR]
        < PREFILTER_BLUR_LAPLACIAN_VAR_THRESHOLD
    ):
        flags.add(RISK_FLAG_BLURRY_IMAGE)
    if (
        measurements[PREFILTER_KEY_MEAN_BRIGHTNESS]
        < PREFILTER_MEAN_BRIGHTNESS_LOW_THRESHOLD
        or measurements[PREFILTER_KEY_GLARE_FRACTION]
        > PREFILTER_GLARE_FRACTION_THRESHOLD
    ):
        flags.add(RISK_FLAG_LOW_LIGHT_OR_GLARE)
    if (
        measurements[PREFILTER_KEY_WIDTH] < PREFILTER_MIN_IMAGE_WIDTH
        or measurements[PREFILTER_KEY_HEIGHT] < PREFILTER_MIN_IMAGE_HEIGHT
    ):
        flags.add(RISK_FLAG_CROPPED_OR_OBSTRUCTED)
    return flags


def dedup_images(images: Sequence[ImageRef]) -> DedupResult:
    """Drop perceptual-hash duplicates before VLM input construction.

    Args:
        images: Image ID/path pairs in claim order.

    Returns:
        A dictionary containing kept image IDs, kept image tuples, and a mapping
        from dropped duplicate image ID to the kept image ID it matched.
    """
    kept_images: List[ImageRef] = []
    kept_hashes: List[Tuple[str, imagehash.ImageHash]] = []
    dropped_duplicates: Dict[str, str] = {}

    for image_id, path in images:
        try:
            with Image.open(path) as image:
                candidate_hash = imagehash.phash(image)
        except (OSError, UnidentifiedImageError):
            kept_images.append((image_id, Path(path)))
            continue

        duplicate_of = None
        for kept_image_id, kept_hash in kept_hashes:
            if candidate_hash - kept_hash <= PREFILTER_PHASH_DUPLICATE_DISTANCE_THRESHOLD:
                duplicate_of = kept_image_id
                break

        if duplicate_of is None:
            kept_hashes.append((image_id, candidate_hash))
            kept_images.append((image_id, Path(path)))
        else:
            dropped_duplicates[image_id] = duplicate_of

    return {
        PREFILTER_KEY_KEPT_IMAGE_IDS: tuple(image_id for image_id, _ in kept_images),
        PREFILTER_KEY_KEPT_IMAGES: tuple(kept_images),
        PREFILTER_KEY_DROPPED_DUPLICATES: dropped_duplicates,
    }


def exif_nonoriginal_signal(path: Path) -> ExifSignal:
    """Extract cheap EXIF and dimension signals for possible non-original images.

    Args:
        path: Local image path to inspect with Pillow.

    Returns:
        A structured signal dictionary. This is only grounding for the VLM; it
        does not directly decide non_original_image (design §5.1-5.2).
    """
    image_path = Path(path)
    reasons: List[str] = []
    signal_score = PREFILTER_DEFAULT_SIGNAL_SCORE
    missing_camera_exif = True
    editor_software = False
    screenshot_dimensions = False

    try:
        with Image.open(image_path) as image:
            exif = image.getexif()
            width, height = image.size
            missing_camera_exif = not any(tag_id in exif for tag_id in EXIF_CAMERA_TAG_IDS)
            software_value = str(exif.get(EXIF_SOFTWARE_TAG_ID, "")).lower()
    except (OSError, UnidentifiedImageError):
        width = PREFILTER_DEFAULT_IMAGE_DIMENSION
        height = PREFILTER_DEFAULT_IMAGE_DIMENSION
        software_value = ""

    if missing_camera_exif:
        reasons.append(EXIF_REASON_MISSING_CAMERA)
        signal_score += EXIF_MISSING_CAMERA_SIGNAL_SCORE

    if any(marker in software_value for marker in EXIF_EDITOR_SOFTWARE_MARKERS):
        editor_software = True
        reasons.append(EXIF_REASON_EDITOR_SOFTWARE)
        signal_score += EXIF_EDITOR_SOFTWARE_SIGNAL_SCORE

    long_edge = max(width, height)
    short_edge = min(width, height)
    if short_edge:
        aspect_ratio = width / height
        screenshot_dimensions = (
            long_edge >= EXIF_SCREENSHOT_LONG_EDGE_MIN
            and (
                aspect_ratio >= EXIF_SCREENSHOT_WIDE_ASPECT_RATIO
                or aspect_ratio <= EXIF_SCREENSHOT_TALL_ASPECT_RATIO
            )
        )
    if screenshot_dimensions:
        reasons.append(EXIF_REASON_SCREENSHOT_DIMENSIONS)
        signal_score += EXIF_SCREENSHOT_DIMENSION_SIGNAL_SCORE

    return {
        PREFILTER_KEY_NON_ORIGINAL_SIGNAL: (
            signal_score >= EXIF_NON_ORIGINAL_SIGNAL_SCORE_THRESHOLD
        ),
        PREFILTER_KEY_SIGNAL_SCORE: signal_score,
        PREFILTER_KEY_SIGNAL_REASONS: tuple(reasons),
        PREFILTER_KEY_MISSING_CAMERA_EXIF: missing_camera_exif,
        PREFILTER_KEY_EDITOR_SOFTWARE: editor_software,
        PREFILTER_KEY_SCREENSHOT_DIMENSIONS: screenshot_dimensions,
    }


def prefilter_claim(images: Sequence[ImageRef]) -> PrefilterResult:
    """Run all Phase 2 programmatic checks for one claim image set.

    Args:
        images: Image ID/path pairs resolved by io_loaders.resolve_image_paths().

    Returns:
        A claim-level pre-filter result containing per-image measurements and
        flags, deduplication output, and an all_images_dead short-circuit signal.
    """
    per_image: List[Measurement] = []
    dedup_candidates: List[ImageRef] = []

    for image_id, path in images:
        measurements = measure_image(path)
        flags = flag_image(measurements)
        exif_signal = exif_nonoriginal_signal(path)
        per_image.append(
            {
                PREFILTER_KEY_IMAGE_ID: image_id,
                PREFILTER_KEY_PATH: str(Path(path)),
                **measurements,
                PREFILTER_KEY_FLAGS: tuple(sorted(flags)),
                PREFILTER_KEY_EXIF: exif_signal,
            }
        )
        if measurements[PREFILTER_KEY_DECODE_OK]:
            dedup_candidates.append((image_id, Path(path)))

    dedup_result = dedup_images(dedup_candidates)
    all_images_dead = all(
        (
            not image_result[PREFILTER_KEY_DECODE_OK]
            or image_result[PREFILTER_KEY_MEAN_BRIGHTNESS]
            <= PREFILTER_DEAD_MEAN_BRIGHTNESS_THRESHOLD
        )
        for image_result in per_image
    )
    return {
        PREFILTER_KEY_PER_IMAGE: tuple(per_image),
        PREFILTER_KEY_DEDUP: dedup_result,
        PREFILTER_KEY_ALL_IMAGES_DEAD: all_images_dead,
    }


def run_smoke_test() -> None:
    """Exercise Phase 2 checks on sample images without invoking a model.

    Raises:
        AssertionError: If measurement, flagging, EXIF signal, deduplication,
            or claim-level prefilter behavior violates Phase 2 invariants.
    """
    sample_rows = load_sample_claims(SAMPLE_CSV)
    first_row_images = resolve_image_paths(sample_rows[0][COL_IMAGE_PATHS])
    assert first_row_images

    first_image_id, first_image_path = first_row_images[0]
    measurements = measure_image(first_image_path)
    assert measurements[PREFILTER_KEY_DECODE_OK]
    assert measurements[PREFILTER_KEY_WIDTH] >= PREFILTER_MIN_IMAGE_WIDTH
    assert measurements[PREFILTER_KEY_HEIGHT] >= PREFILTER_MIN_IMAGE_HEIGHT
    assert isinstance(flag_image(measurements), set)
    assert (
        exif_nonoriginal_signal(first_image_path)[PREFILTER_KEY_SIGNAL_SCORE]
        >= PREFILTER_DEFAULT_SIGNAL_SCORE
    )

    dedup_result = dedup_images(
        (
            (first_image_id, first_image_path),
            (first_image_id + PREFILTER_DUPLICATE_TEST_SUFFIX, first_image_path),
        )
    )
    assert len(dedup_result[PREFILTER_KEY_KEPT_IMAGE_IDS]) == 1
    assert dedup_result[PREFILTER_KEY_DROPPED_DUPLICATES]

    claim_result = prefilter_claim(first_row_images)
    assert claim_result[PREFILTER_KEY_PER_IMAGE]
    assert not claim_result[PREFILTER_KEY_ALL_IMAGES_DEAD]


if __name__ == "__main__":
    run_smoke_test()
