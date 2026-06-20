"""
cache.py - Stable content-hash result cache.

WHAT:  This module computes cache keys from claim-row fields, image bytes, and
       the prompt version, then persists and loads model results.
WHY:   Local caching makes re-runs deterministic and avoids unnecessary Claude
       calls during evaluation and final output generation.
STEPS: Implements STEPS.md Phase 6 item 3.
IN:    Claim rows, resolved image paths, prompt version, and model responses.
OUT:   Stable cache keys and cached response records.
"""

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple

from constants import (
    CACHE_DIR,
    CACHE_FILE_SUFFIX,
    CACHE_JSON_INDENT,
    CACHE_KEY_IMAGE_ID,
    CACHE_KEY_IMAGE_SHA256,
    CACHE_KEY_IMAGES,
    CACHE_KEY_PROMPT_VERSION,
    CACHE_KEY_ROW,
    CACHE_KEY_VERSION,
    CACHE_KEY_VERSION_VALUE,
    COL_IMAGE_PATHS,
    PROMPT_VERSION,
    SAMPLE_CSV,
)
from io_loaders import load_sample_claims, resolve_image_paths


ImageRef = Tuple[str, Path]
CacheRecord = Dict[str, Any]


def _json_bytes(value: Any) -> bytes:
    """Serialize cache inputs with stable ordering and UTF-8 bytes.

    Stable serialization is required because the cache key must be identical on
    repeated runs for the same row, image bytes, and prompt version.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _image_digest(image: ImageRef) -> Dict[str, str]:
    """Hash one image's bytes for inclusion in a content key.

    The key depends on image bytes, not filesystem metadata, so moving the repo
    without changing images does not invalidate cached model responses.
    """
    image_id, path = image
    return {
        CACHE_KEY_IMAGE_ID: image_id,
        CACHE_KEY_IMAGE_SHA256: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
    }


def cache_key(
    claim_row: Mapping[str, Any],
    images: Iterable[ImageRef],
    prompt_version: str = PROMPT_VERSION,
) -> str:
    """Return a stable content hash for a claim/model prompt input.

    Args:
        claim_row: Input row fields used to build the claim prompt.
        images: Resolved `(image_id, path)` pairs in prompt order.
        prompt_version: Prompt version included so prompt changes invalidate
            existing responses.

    Returns:
        A hex SHA-256 cache key.
    """
    payload = {
        CACHE_KEY_VERSION: CACHE_KEY_VERSION_VALUE,
        CACHE_KEY_PROMPT_VERSION: prompt_version,
        CACHE_KEY_ROW: dict(sorted((str(key), claim_row[key]) for key in claim_row)),
        CACHE_KEY_IMAGES: [_image_digest((image_id, Path(path))) for image_id, path in images],
    }
    return hashlib.sha256(_json_bytes(payload)).hexdigest()


def _cache_path(key: str, cache_dir: Path = CACHE_DIR) -> Path:
    """Map a cache key to its JSON file path.

    Keeping this mapping in one helper makes the persistence functions small and
    keeps the file naming convention tied to constants.py.
    """
    return Path(cache_dir) / f"{key}{CACHE_FILE_SUFFIX}"


def load_cached_response(key: str, cache_dir: Path = CACHE_DIR) -> CacheRecord | None:
    """Load a cached model response when present.

    Args:
        key: Cache key from cache_key().
        cache_dir: Directory containing response JSON files.

    Returns:
        Cached response dictionary, or None when the key is absent.
    """
    path = _cache_path(key, cache_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_cached_response(
    key: str,
    response: Mapping[str, Any],
    cache_dir: Path = CACHE_DIR,
) -> Path:
    """Persist one model response under its content hash key.

    Args:
        key: Cache key from cache_key().
        response: JSON-serializable model or aggregate response.
        cache_dir: Directory where the response file should be written.

    Returns:
        Path to the written cache file.
    """
    cache_path = _cache_path(key, cache_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            dict(response),
            indent=CACHE_JSON_INDENT,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return cache_path


def run_smoke_test() -> None:
    """Exercise stable cache keys and response round-tripping.

    Raises:
        AssertionError: If cache keys change across repeated calls or written
            records do not load back identically.
    """
    first_row = load_sample_claims(SAMPLE_CSV)[0]
    images = resolve_image_paths(first_row[COL_IMAGE_PATHS])
    first_key = cache_key(first_row, images)
    second_key = cache_key(first_row, images)
    assert first_key == second_key

    response = {"ok": True, "key": first_key}
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir)
        assert load_cached_response(first_key, cache_dir) is None
        cache_path = write_cached_response(first_key, response, cache_dir)
        assert cache_path.exists()
        assert load_cached_response(first_key, cache_dir) == response


if __name__ == "__main__":
    run_smoke_test()
