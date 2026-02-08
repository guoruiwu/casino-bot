"""
Screen interaction layer: screenshot capture, image matching (OpenCV), and OCR (Tesseract).

Handles macOS Retina display scaling automatically — Pillow captures at 2x resolution
while PyAutoGUI operates at 1x logical coordinates.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import pyautogui
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

# macOS Retina displays capture at 2x resolution.
# Detect scale factor once at import time.
_RETINA_SCALE: int = 2


def _get_retina_scale() -> int:
    """Detect Retina scale factor by comparing Pillow screenshot size to PyAutoGUI screen size."""
    try:
        screen_w, screen_h = pyautogui.size()
        screenshot = pyautogui.screenshot()
        pil_w, _ = screenshot.size
        scale = pil_w // screen_w
        return max(scale, 1)
    except Exception:
        return 2  # Default to 2x on macOS


def init_retina_scale() -> int:
    """Initialize the Retina scale factor. Call once at startup."""
    global _RETINA_SCALE
    _RETINA_SCALE = _get_retina_scale()
    logger.info(f"Retina scale factor: {_RETINA_SCALE}")
    return _RETINA_SCALE


def take_screenshot(region: Optional[dict] = None) -> np.ndarray:
    """
    Capture the screen (or a region) and return as a BGR numpy array for OpenCV.

    Args:
        region: Optional dict with keys x, y, w, h in logical (PyAutoGUI) coordinates.
                If None, captures the full screen.

    Returns:
        numpy array in BGR color format (OpenCV convention).
    """
    if region:
        # Convert logical coordinates to Pillow/retina pixel coordinates
        pil_region = (
            region["x"] * _RETINA_SCALE,
            region["y"] * _RETINA_SCALE,
            (region["x"] + region["w"]) * _RETINA_SCALE,
            (region["y"] + region["h"]) * _RETINA_SCALE,
        )
        screenshot = pyautogui.screenshot()
        screenshot = screenshot.crop(pil_region)
    else:
        screenshot = pyautogui.screenshot()

    # Convert PIL Image to numpy BGR array for OpenCV
    img_rgb = np.array(screenshot)
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    return img_bgr


def _load_template(template_path: str | Path) -> np.ndarray:
    """Load a template image from disk as a BGR numpy array."""
    path = str(template_path)
    template = cv2.imread(path, cv2.IMREAD_COLOR)
    if template is None:
        raise FileNotFoundError(f"Template image not found: {path}")
    return template


def find_element(
    template_path: str | Path,
    confidence: float = 0.8,
    screenshot: Optional[np.ndarray] = None,
) -> Optional[tuple[int, int]]:
    """
    Find a UI element on screen using OpenCV template matching.

    Args:
        template_path: Path to the template PNG image.
        confidence: Minimum match confidence (0-1). Higher = stricter.
        screenshot: Optional pre-captured screenshot. If None, captures a new one.

    Returns:
        (x, y) center coordinates in logical (PyAutoGUI) space, or None if not found.
    """
    if screenshot is None:
        screenshot = take_screenshot()

    template = _load_template(template_path)
    result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= confidence:
        # max_loc is top-left corner in pixel coordinates
        t_h, t_w = template.shape[:2]
        center_x = max_loc[0] + t_w // 2
        center_y = max_loc[1] + t_h // 2

        # Convert from retina pixel coordinates to logical PyAutoGUI coordinates
        logical_x = center_x // _RETINA_SCALE
        logical_y = center_y // _RETINA_SCALE

        logger.debug(
            f"Found {template_path} at ({logical_x}, {logical_y}) "
            f"confidence={max_val:.3f}"
        )
        return (logical_x, logical_y)

    logger.debug(f"Not found: {template_path} (best={max_val:.3f}, need={confidence})")
    return None


def find_all_elements(
    template_path: str | Path,
    confidence: float = 0.8,
    min_distance: int = 20,
    screenshot: Optional[np.ndarray] = None,
) -> list[tuple[int, int]]:
    """
    Find all instances of a UI element on screen.

    Useful for pick-and-click bonus rounds where multiple identical items appear.

    Args:
        template_path: Path to the template PNG image.
        confidence: Minimum match confidence (0-1).
        min_distance: Minimum pixel distance between matches (to avoid duplicates).
        screenshot: Optional pre-captured screenshot.

    Returns:
        List of (x, y) center coordinates in logical (PyAutoGUI) space.
    """
    if screenshot is None:
        screenshot = take_screenshot()

    template = _load_template(template_path)
    result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)

    # Find all locations above threshold
    locations = np.where(result >= confidence)
    t_h, t_w = template.shape[:2]

    # Collect raw matches
    raw_matches = []
    for pt_y, pt_x in zip(*locations):
        center_x = pt_x + t_w // 2
        center_y = pt_y + t_h // 2
        score = result[pt_y, pt_x]
        raw_matches.append((center_x, center_y, float(score)))

    # Sort by confidence descending
    raw_matches.sort(key=lambda m: m[2], reverse=True)

    # Non-maximum suppression: filter out matches too close to a better match
    filtered = []
    min_dist_px = min_distance * _RETINA_SCALE
    for cx, cy, score in raw_matches:
        too_close = False
        for fx, fy, _ in filtered:
            if abs(cx - fx) < min_dist_px and abs(cy - fy) < min_dist_px:
                too_close = True
                break
        if not too_close:
            filtered.append((cx, cy, score))

    # Convert to logical coordinates
    results = []
    for cx, cy, score in filtered:
        logical_x = cx // _RETINA_SCALE
        logical_y = cy // _RETINA_SCALE
        results.append((logical_x, logical_y))

    logger.debug(f"Found {len(results)} instances of {template_path}")
    return results


def read_text(region: dict, preprocess: str = "thresh") -> str:
    """
    Read text from a screen region using OCR (Tesseract).

    Args:
        region: Dict with keys x, y, w, h in logical (PyAutoGUI) coordinates.
        preprocess: Preprocessing method — "thresh" for thresholding (good for dark
                    backgrounds), "blur" for Gaussian blur, or "none".

    Returns:
        Extracted text string, stripped of whitespace.
    """
    screenshot = take_screenshot(region)

    # Convert to grayscale
    gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

    # Preprocessing to improve OCR accuracy
    if preprocess == "thresh":
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    elif preprocess == "blur":
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # Scale up for better OCR accuracy on small text
    scale = 2
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Run Tesseract OCR
    text = pytesseract.image_to_string(gray, config="--psm 7")  # Single line mode

    cleaned = text.strip()
    logger.debug(f"OCR region {region}: '{cleaned}'")
    return cleaned


def read_number(region: dict) -> Optional[float]:
    """
    Read a numeric value (like balance or bet amount) from a screen region.

    Handles common OCR quirks with numbers: $ signs, commas, spaces.

    Args:
        region: Dict with keys x, y, w, h in logical coordinates.

    Returns:
        Parsed float value, or None if OCR failed to produce a valid number.
    """
    text = read_text(region)

    # Clean up common OCR artifacts in numbers
    cleaned = text.replace("$", "").replace(",", "").replace(" ", "").strip()

    # Remove any non-numeric characters except dots
    numeric = ""
    for ch in cleaned:
        if ch.isdigit() or ch == ".":
            numeric += ch

    if not numeric:
        logger.warning(f"Could not parse number from OCR text: '{text}'")
        return None

    try:
        return float(numeric)
    except ValueError:
        logger.warning(f"Could not convert to float: '{numeric}' (raw: '{text}')")
        return None


def wait_for_element(
    template_path: str | Path,
    confidence: float = 0.8,
    timeout: float = 30.0,
    poll_interval: float = 1.0,
) -> Optional[tuple[int, int]]:
    """
    Poll the screen until a UI element appears or timeout.

    Args:
        template_path: Path to the template PNG image.
        confidence: Minimum match confidence.
        timeout: Maximum seconds to wait.
        poll_interval: Seconds between checks.

    Returns:
        (x, y) center in logical coordinates if found, or None on timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        pos = find_element(template_path, confidence)
        if pos is not None:
            return pos
        time.sleep(poll_interval)

    logger.warning(f"Timeout waiting for {template_path} after {timeout}s")
    return None


def wait_for_any_element(
    templates: dict[str, str | Path],
    confidence: float = 0.8,
    timeout: float = 30.0,
    poll_interval: float = 1.0,
) -> Optional[tuple[str, tuple[int, int]]]:
    """
    Poll the screen until any of several UI elements appears.

    Useful for state detection (e.g. waiting for either bonus screen or normal result).

    Args:
        templates: Dict mapping name -> template_path.
        confidence: Minimum match confidence.
        timeout: Maximum seconds to wait.
        poll_interval: Seconds between checks.

    Returns:
        Tuple of (matched_name, (x, y)) if found, or None on timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        screenshot = take_screenshot()
        for name, path in templates.items():
            pos = find_element(path, confidence, screenshot=screenshot)
            if pos is not None:
                logger.info(f"Detected: {name}")
                return (name, pos)
        time.sleep(poll_interval)

    names = list(templates.keys())
    logger.warning(f"Timeout waiting for any of {names} after {timeout}s")
    return None


def element_exists(
    template_path: str | Path,
    confidence: float = 0.8,
    screenshot: Optional[np.ndarray] = None,
) -> bool:
    """Quick check if an element is currently visible on screen."""
    return find_element(template_path, confidence, screenshot=screenshot) is not None
