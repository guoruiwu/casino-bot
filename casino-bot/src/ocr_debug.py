"""
OCR debug utilities: preprocessing pipeline, always-on snapshot capture, and
disk rotation.

The preprocessing pipeline is extracted here as the single source of truth so
both ``screen.read_text()`` and the debug snapshot saver use the same logic.

Snapshots are saved on every OCR read (not just failures) so you can build a
labeled dataset for optimising preprocessing.  Automatic rotation keeps disk
usage bounded.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Default directory for OCR snapshots, relative to project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SNAPSHOT_DIR = _PROJECT_ROOT / "debug" / "ocr"

# Default max snapshots per label before rotation kicks in.
DEFAULT_MAX_SNAPSHOTS = 50


# ── Preprocessing Pipeline ────────────────────────────────────────────────


def preprocess_for_ocr(
    img_bgr: np.ndarray,
    preprocess: str = "thresh",
    invert: bool = True,
    border: int = 10,
    scale: int = 2,
) -> np.ndarray:
    """
    Apply the standard OCR preprocessing pipeline to a BGR image.

    This is the single source of truth used by both :func:`screen.read_text`
    and the debug snapshot saver.

    Args:
        img_bgr: Input image in BGR colour format (as returned by
                 ``take_screenshot``).
        preprocess: ``"thresh"`` for OTSU thresholding, ``"blur"`` for
                    Gaussian blur, or ``"none"``.
        invert: If True, automatically invert dark-background images so
                Tesseract sees dark text on white.
        border: Whitespace padding (px) added around the image.
        scale: Upscale factor applied before OCR.

    Returns:
        Processed grayscale image ready for Tesseract.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    if preprocess == "thresh":
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    elif preprocess == "blur":
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

    if invert and np.mean(gray) < 127:
        gray = cv2.bitwise_not(gray)

    if scale > 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    if border > 0:
        gray = cv2.copyMakeBorder(
            gray, border, border, border, border,
            cv2.BORDER_CONSTANT, value=255,
        )

    return gray


# ── Snapshot Capture ──────────────────────────────────────────────────────


def save_ocr_snapshot(
    raw_img: np.ndarray,
    processed_img: np.ndarray,
    label: str,
    *,
    region: Optional[dict] = None,
    ocr_text: str = "",
    parsed_value: Any = None,
    success: bool = False,
    invert: bool = True,
    pipeline: str = "thresh",
    snapshot_dir: Optional[Path] = None,
    max_snapshots: int = DEFAULT_MAX_SNAPSHOTS,
) -> None:
    """
    Save an OCR snapshot (raw crop + processed crop + JSON metadata).

    Called on **every** OCR read so both successes and failures are captured
    for later analysis.

    Args:
        raw_img: Raw BGR screenshot of the OCR region (already cropped).
        processed_img: Preprocessed grayscale image fed to Tesseract.
        label: Region name, e.g. ``"player_total"`` or ``"dealer_total"``.
        region: Dict with x, y, w, h (logged in metadata).
        ocr_text: Raw text returned by Tesseract.
        parsed_value: The validated/parsed value (int, tuple, etc.), or None.
        success: Whether the OCR read was considered successful.
        invert: Whether inversion was used for this read.
        pipeline: Preprocessing method name (e.g. ``"thresh"``).
        snapshot_dir: Override snapshot directory (defaults to ``debug/ocr/``).
        max_snapshots: Max snapshots per label before oldest are deleted.
    """
    try:
        out_dir = snapshot_dir or _DEFAULT_SNAPSHOT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        base_name = f"{label}_{timestamp}"

        # Save raw region crop
        raw_path = out_dir / f"{base_name}_raw.png"
        cv2.imwrite(str(raw_path), raw_img)

        # Save processed region crop
        processed_path = out_dir / f"{base_name}_processed.png"
        cv2.imwrite(str(processed_path), processed_img)

        # Save JSON metadata sidecar
        meta = {
            "timestamp": timestamp,
            "label": label,
            "region": region,
            "ocr_text": ocr_text,
            "parsed_value": _serialise_value(parsed_value),
            "success": success,
            "invert": invert,
            "pipeline": pipeline,
        }
        meta_path = out_dir / f"{base_name}.json"
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")

        logger.debug(f"OCR snapshot saved: {base_name} (success={success})")

        # Rotate old snapshots for this label
        rotate_snapshots(label, max_snapshots=max_snapshots, snapshot_dir=out_dir)

    except Exception as e:
        logger.warning(f"Failed to save OCR snapshot for '{label}': {e}")


def _serialise_value(value: Any) -> Any:
    """Make parsed_value JSON-safe (tuples → lists, etc.)."""
    if isinstance(value, tuple):
        return list(value)
    return value


# ── Disk Rotation ─────────────────────────────────────────────────────────


def rotate_snapshots(
    label: str,
    max_snapshots: int = DEFAULT_MAX_SNAPSHOTS,
    snapshot_dir: Optional[Path] = None,
) -> None:
    """
    Delete the oldest snapshots for *label* when the count exceeds
    *max_snapshots*.

    Each snapshot consists of up to three files (``_raw.png``,
    ``_processed.png``, ``.json``) sharing the same base name.  We count
    by unique base names and delete the oldest groups first.

    Args:
        label: Region name prefix (e.g. ``"player_total"``).
        max_snapshots: Keep at most this many snapshot groups.
        snapshot_dir: Override directory (defaults to ``debug/ocr/``).
    """
    out_dir = snapshot_dir or _DEFAULT_SNAPSHOT_DIR
    if not out_dir.is_dir():
        return

    # Collect all _raw.png files for this label (one per snapshot group)
    raw_files = sorted(out_dir.glob(f"{label}_*_raw.png"))

    if len(raw_files) <= max_snapshots:
        return

    # Number of groups to delete
    to_delete = len(raw_files) - max_snapshots

    for raw_path in raw_files[:to_delete]:
        # Derive sibling file names from the raw path
        base = str(raw_path).replace("_raw.png", "")
        for suffix in ("_raw.png", "_processed.png", ".json"):
            path = Path(base + suffix)
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass

    logger.debug(f"Rotated {to_delete} old OCR snapshot(s) for '{label}'")
