#!/usr/bin/env python3
"""
Simple capture tool — only grabs the 2 screenshots needed for Crazy Time simple mode.

Usage:
  python3 tools/capture_simple.py --game crazy_time_dk

Steps:
  1. Open Crazy Time in your browser
  2. Wait for a BETTING phase
  3. The tool asks you to select just 2 things:
     a) The "betting open" indicator (any text/icon that only shows during betting)
     b) The "1" bet area (the clickable region for betting on 1)
  4. Done! Run the bot.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.screen import init_retina_scale, take_screenshot


def wait_for_click(prompt: str) -> tuple[int, int]:
    """Show prompt, wait for Enter, return current mouse position."""
    input(f"  {prompt}")
    pos = pyautogui.position()
    print(f"  → Position: ({pos.x}, {pos.y})")
    return (pos.x, pos.y)


def capture_region(name: str, description: str, asset_dir: Path) -> bool:
    """Capture a screen region by clicking two corners."""
    print(f"\n  [{name}] {description}")
    print(f"  Move your mouse to the TOP-LEFT corner of the element.")
    pos1 = wait_for_click("Press Enter when ready...")

    print(f"  Now move to the BOTTOM-RIGHT corner.")
    pos2 = wait_for_click("Press Enter when ready...")

    # Take screenshot and crop
    screenshot = take_screenshot()
    scale = 2  # Retina

    x1 = min(pos1[0], pos2[0]) * scale
    y1 = min(pos1[1], pos2[1]) * scale
    x2 = max(pos1[0], pos2[0]) * scale
    y2 = max(pos1[1], pos2[1]) * scale

    if x2 - x1 < 4 or y2 - y1 < 4:
        print("  ✗ Region too small — try again")
        return False

    cropped = screenshot[y1:y2, x1:x2]
    filepath = asset_dir / f"{name}.png"
    cv2.imwrite(str(filepath), cropped)
    print(f"  ✓ Saved: {filepath}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Simple Crazy Time asset capture")
    parser.add_argument("--game", default="crazy_time_dk", help="Game name for asset directory")
    args = parser.parse_args()

    asset_dir = PROJECT_ROOT / "assets" / args.game
    asset_dir.mkdir(parents=True, exist_ok=True)

    init_retina_scale()

    print()
    print("=" * 50)
    print("  Crazy Time Simple — Quick Setup")
    print("=" * 50)
    print()
    print("  Open Crazy Time in your browser and wait for")
    print("  a BETTING phase (when you can place bets).")
    print()
    print("  You only need to capture 2 things:")
    print("    1. The 'betting open' indicator")
    print("    2. The '1' bet area")
    print()
    input("  Press Enter when the game is in a betting phase...")

    # Capture betting_open indicator
    ok1 = capture_region(
        "betting_open",
        "Any text/icon that ONLY appears during betting\n"
        "  (e.g. a timer, 'PLACE YOUR BETS', countdown, etc.)",
        asset_dir,
    )

    # Capture bet_1 area
    ok2 = capture_region(
        "bet_1",
        "The '1' bet area (the button/region you click to bet on 1)",
        asset_dir,
    )

    print()
    if ok1 and ok2:
        config_path = f"config/games/{args.game}_simple.yaml"
        print("  ✓ All done! Only 2 screenshots needed.")
        print()
        print(f"  Run the bot:")
        print(f"    python3 main.py --config {config_path} --duration 60")
    else:
        print("  Some captures failed. Run this tool again to retry.")

    print()


if __name__ == "__main__":
    main()
