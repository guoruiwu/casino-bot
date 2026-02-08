"""
Action layer: mouse/keyboard control with human-like behavior.

Wraps PyAutoGUI with random delays, jitter, and element-aware clicking.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Optional

import pyautogui

from src.screen import find_element, find_all_elements, wait_for_element

logger = logging.getLogger(__name__)

# Safety: PyAutoGUI moves mouse to corner to abort if something goes wrong
pyautogui.FAILSAFE = True
# Disable PyAutoGUI's built-in pause (we handle our own delays)
pyautogui.PAUSE = 0.05


def random_delay(min_s: float = 0.3, max_s: float = 1.0) -> None:
    """Sleep for a random duration between min_s and max_s seconds."""
    delay = random.uniform(min_s, max_s)
    logger.debug(f"Delay: {delay:.2f}s")
    time.sleep(delay)


def add_jitter(x: int, y: int, max_offset: int = 5) -> tuple[int, int]:
    """
    Add small random offset to coordinates to appear more human.

    Args:
        x, y: Original coordinates.
        max_offset: Maximum pixel offset in each direction.

    Returns:
        (x, y) with random jitter applied.
    """
    jx = x + random.randint(-max_offset, max_offset)
    jy = y + random.randint(-max_offset, max_offset)
    return (jx, jy)


def click_position(
    x: int,
    y: int,
    jitter: bool = True,
    delay_range: Optional[tuple[float, float]] = None,
) -> None:
    """
    Click at a specific screen position with optional jitter and delay.

    Args:
        x, y: Logical (PyAutoGUI) screen coordinates.
        jitter: Whether to add small random offset.
        delay_range: Optional (min, max) seconds to wait after clicking.
    """
    if jitter:
        x, y = add_jitter(x, y)

    logger.info(f"Click at ({x}, {y})")
    pyautogui.click(x, y)

    if delay_range:
        random_delay(*delay_range)


def click_element(
    template_path: str | Path,
    confidence: float = 0.8,
    jitter: bool = True,
    delay_range: Optional[tuple[float, float]] = None,
) -> bool:
    """
    Find a UI element on screen and click it.

    Args:
        template_path: Path to the template PNG image.
        confidence: Minimum match confidence.
        jitter: Whether to add random offset to click position.
        delay_range: Optional (min, max) seconds to wait after clicking.

    Returns:
        True if element was found and clicked, False otherwise.
    """
    pos = find_element(template_path, confidence)
    if pos is None:
        logger.warning(f"Cannot click — element not found: {template_path}")
        return False

    click_position(pos[0], pos[1], jitter=jitter, delay_range=delay_range)
    return True


def click_element_and_wait(
    template_path: str | Path,
    confidence: float = 0.8,
    timeout: float = 10.0,
    poll_interval: float = 1.0,
    jitter: bool = True,
    delay_range: Optional[tuple[float, float]] = None,
) -> bool:
    """
    Wait for a UI element to appear, then click it.

    Args:
        template_path: Path to the template PNG image.
        confidence: Minimum match confidence.
        timeout: Max seconds to wait for element to appear.
        poll_interval: Seconds between checks.
        jitter: Whether to add random offset.
        delay_range: Optional post-click delay.

    Returns:
        True if element was found and clicked, False on timeout.
    """
    pos = wait_for_element(template_path, confidence, timeout, poll_interval)
    if pos is None:
        return False

    click_position(pos[0], pos[1], jitter=jitter, delay_range=delay_range)
    return True


def click_region_random(region: dict) -> None:
    """
    Click a random point within a defined screen region.

    Useful for Cash Hunt bonus grid or pick-and-click bonus items.

    Args:
        region: Dict with keys x, y, w, h in logical coordinates.
    """
    x = random.randint(region["x"], region["x"] + region["w"])
    y = random.randint(region["y"], region["y"] + region["h"])
    logger.info(f"Random click in region ({region}) at ({x}, {y})")
    pyautogui.click(x, y)


def click_all_elements(
    template_path: str | Path,
    confidence: float = 0.8,
    delay_between: tuple[float, float] = (0.3, 0.8),
    jitter: bool = True,
) -> int:
    """
    Find and click all instances of a UI element.

    Useful for pick-and-click bonus rounds where you need to click multiple items.

    Args:
        template_path: Path to the template image.
        confidence: Match confidence.
        delay_between: (min, max) seconds to wait between clicks.
        jitter: Whether to add random offset.

    Returns:
        Number of elements clicked.
    """
    positions = find_all_elements(template_path, confidence)
    if not positions:
        logger.debug(f"No elements found to click: {template_path}")
        return 0

    # Shuffle to vary click order
    random.shuffle(positions)

    for i, (x, y) in enumerate(positions):
        click_position(x, y, jitter=jitter)
        if i < len(positions) - 1:
            random_delay(*delay_between)

    logger.info(f"Clicked {len(positions)} instances of {template_path}")
    return len(positions)


def move_mouse_away() -> None:
    """Move the mouse to a neutral position to avoid hovering over UI elements."""
    screen_w, screen_h = pyautogui.size()
    # Move to bottom-right area, away from game UI
    x = screen_w - 50 + random.randint(-10, 10)
    y = screen_h - 50 + random.randint(-10, 10)
    pyautogui.moveTo(x, y, duration=0.2)
