#!/usr/bin/env python3
"""
Asset capture tool for setting up new games.

Usage:
  # Capture assets for a new slot game
  python3 tools/capture.py --game my_slot_dk --type slot

  # Capture assets for Crazy Time
  python3 tools/capture.py --game crazy_time_dk --type crazy_time

  # Test if all assets for a game can be found on screen
  python3 tools/capture.py --test my_slot_dk

How it works:
  1. Takes a screenshot of your current screen
  2. For each required element, you position your mouse on the corners and press Enter
  3. Saves cropped PNGs and generates a starter YAML config

Only captures what's actually needed — most games need just 2-3 elements.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui
import yaml

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.screen import find_element, init_retina_scale, take_screenshot

# ── Element definitions per game type ────────────────────────────────────
# Only the ESSENTIAL elements that must be image-matched.
# Everything else (bet positions, regions) uses coordinates in the YAML.

SLOT_ELEMENTS = [
    ("spin_button", "Spin button (the main spin/play button)", True),
]

SLOT_OPTIONAL_ELEMENTS = [
    ("bet_up", "Bet increase button (+ or up arrow)"),
    ("bet_down", "Bet decrease button (- or down arrow)"),
    ("autoplay_button", "Autoplay button"),
    ("autoplay_confirm", "Autoplay confirm/start button"),
    ("autoplay_stop", "Autoplay stop/cancel button"),
    ("autoplay_active", "Autoplay active indicator"),
    ("bonus_free_spins", "Free spins indicator/overlay"),
    ("bonus_pick", "Pick-and-click bonus screen indicator"),
    ("bonus_wheel", "Wheel bonus indicator"),
    ("pick_target", "A clickable item in the pick bonus"),
    ("pick_collect", "Collect/end indicator for pick bonus"),
]

CRAZY_TIME_ELEMENTS = [
    ("betting_open", "Betting open indicator (shows when bets are accepted)", True),
]

CRAZY_TIME_OPTIONAL_ELEMENTS = [
    ("bonus_cashhunt", "Cash Hunt bonus screen indicator"),
]

SLOT_REGIONS = [
    ("balance", "Balance display area (the number showing your balance)"),
    ("bet_amount", "Bet amount display area (shows current bet per spin)"),
]

CRAZY_TIME_REGIONS = [
    ("balance", "Balance display area"),
]


def reset_game(game_name: str) -> None:
    """Delete all screenshots and config for a game."""
    import shutil

    asset_dir = PROJECT_ROOT / "assets" / game_name
    config_path = PROJECT_ROOT / "config" / "games" / f"{game_name}.yaml"

    deleted = []
    if asset_dir.exists():
        shutil.rmtree(asset_dir)
        deleted.append(str(asset_dir))
    if config_path.exists():
        config_path.unlink()
        deleted.append(str(config_path))

    if deleted:
        print(f"\n  Reset '{game_name}' — deleted:")
        for d in deleted:
            print(f"    {d}")
        print()
    else:
        print(f"\n  Nothing to reset for '{game_name}'.\n")


def capture_screenshot_region() -> tuple[np.ndarray, dict] | None:
    """
    Let the user select a region on screen by clicking two corners.

    Returns:
        Tuple of (cropped image as numpy array, region dict) or None if cancelled.
    """
    print("    Position cursor on TOP-LEFT corner, press Enter")
    input("    > ")
    pos1 = pyautogui.position()
    print(f"    Top-left: ({pos1.x}, {pos1.y})")

    print("    Position cursor on BOTTOM-RIGHT corner, press Enter")
    input("    > ")
    pos2 = pyautogui.position()
    print(f"    Bottom-right: ({pos2.x}, {pos2.y})")

    # Take screenshot and crop
    screenshot = take_screenshot()
    scale = 2  # Retina scale

    x1 = min(pos1.x, pos2.x) * scale
    y1 = min(pos1.y, pos2.y) * scale
    x2 = max(pos1.x, pos2.x) * scale
    y2 = max(pos1.y, pos2.y) * scale

    if x2 - x1 < 4 or y2 - y1 < 4:
        print("    Region too small — try again")
        return None

    cropped = screenshot[y1:y2, x1:x2]

    region = {
        "x": min(pos1.x, pos2.x),
        "y": min(pos1.y, pos2.y),
        "w": abs(pos2.x - pos1.x),
        "h": abs(pos2.y - pos1.y),
    }

    return cropped, region


def capture_position(prompt: str) -> tuple[int, int]:
    """Capture a single screen position (for bet click targets)."""
    print(f"    {prompt}")
    input("    > ")
    pos = pyautogui.position()
    print(f"    Position: ({pos.x}, {pos.y})")
    return (pos.x, pos.y)


def capture_elements(game_name: str, game_type: str) -> dict:
    """Walk through capturing elements for a game — only the essentials."""
    asset_dir = PROJECT_ROOT / "assets" / game_name
    asset_dir.mkdir(parents=True, exist_ok=True)

    if game_type == "slot":
        required_elements = SLOT_ELEMENTS
        optional_elements = SLOT_OPTIONAL_ELEMENTS
        regions_list = SLOT_REGIONS
    elif game_type == "crazy_time":
        required_elements = CRAZY_TIME_ELEMENTS
        optional_elements = CRAZY_TIME_OPTIONAL_ELEMENTS
        regions_list = CRAZY_TIME_REGIONS
    else:
        print(f"Unknown game type: {game_type}")
        sys.exit(1)

    captured_elements = {}
    captured_regions = {}
    captured_positions = {}

    print(f"\n{'='*60}")
    print(f"  Capturing assets for: {game_name} ({game_type})")
    print(f"  Asset directory: {asset_dir}")
    print(f"{'='*60}")
    print()
    print("  Make sure the game is open and visible in Chrome.")
    print()

    # ── Step 1: Required elements (image templates) ──
    print(f"--- Required Elements ({len(required_elements)}) ---\n")
    for elem_name, description, _required in required_elements:
        print(f"  [{elem_name}] {description}")
        result = capture_screenshot_region()
        if result is None:
            print("    Failed — try again")
            result = capture_screenshot_region()
        if result is None:
            print("    Skipped (bot may not work correctly without this).\n")
            continue

        img, region = result
        filename = f"{elem_name}.png"
        filepath = asset_dir / filename
        cv2.imwrite(str(filepath), img)
        captured_elements[elem_name] = filename
        print(f"    Saved: {filepath}\n")

    # ── Step 2: Bet position (Crazy Time only) ──
    if game_type == "crazy_time":
        print("\n--- Bet Position ---\n")
        pos = capture_position("Hover over the '1' bet area, press Enter")
        captured_positions["1"] = {"x": pos[0], "y": pos[1]}
        print()

    return {
        "elements": captured_elements,
        "regions": captured_regions,
        "positions": captured_positions,
        "asset_dir": f"assets/{game_name}/",
    }


def generate_yaml_config(game_name: str, game_type: str, captured: dict) -> str:
    """Generate a YAML config file from captured data."""
    config_dir = PROJECT_ROOT / "config" / "games"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / f"{game_name}.yaml"

    if game_type == "slot":
        config = _generate_slot_config(game_name, captured)
    elif game_type == "crazy_time":
        config = _generate_crazy_time_config(game_name, captured)
    else:
        config = {}

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"\n  Config saved: {config_path}")
    return str(config_path)


def _generate_slot_config(game_name: str, captured: dict) -> dict:
    """Generate slot YAML config."""
    return {
        "game": {
            "name": game_name.replace("_", " ").title(),
            "type": "slot",
            "platform": "draftkings",
            "asset_dir": captured.get("asset_dir", f"assets/{game_name}/"),
        },
        "spin_mode": "manual",
        "elements": captured.get("elements", {}),
        "regions": captured.get("regions", {}),
        "settings": {
            "target_bet": 0.20,
            "confidence": 0.85,
            "action_delay": [0.3, 0.8],
            "spin_wait": 3.0,
            "poll_interval": 2.0,
            "session_duration": 60,
        },
        "autoplay": {
            "num_spins": 100,
        },
    }


def _generate_crazy_time_config(game_name: str, captured: dict) -> dict:
    """Generate Crazy Time YAML config."""
    elements = captured.get("elements", {})
    positions = captured.get("positions", {})

    # Build bets list from captured positions
    bets = []
    for segment, pos in positions.items():
        bets.append({
            "segment": segment,
            "click_x": pos["x"],
            "click_y": pos["y"],
        })

    return {
        "game": {
            "name": game_name.replace("_", " ").title(),
            "type": "crazy_time",
            "platform": "draftkings",
            "asset_dir": captured.get("asset_dir", f"assets/{game_name}/"),
        },
        "elements": elements,
        "regions": captured.get("regions", {}),
        "bets": bets,
        "settings": {
            "confidence": 0.85,
            "action_delay": [0.3, 1.0],
            "poll_interval": 2.0,
            "session_duration": 60,
        },
    }


def test_assets(game_name: str) -> None:
    """Test if all captured assets can be found on the current screen."""
    asset_dir = PROJECT_ROOT / "assets" / game_name
    config_dir = PROJECT_ROOT / "config" / "games"

    config_path = config_dir / f"{game_name}.yaml"
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    print(f"\n{'='*60}")
    print(f"  Testing assets for: {game_name}")
    print(f"{'='*60}\n")
    print("  Make sure the game is open and visible in Chrome.\n")

    input("  Press Enter to start test...")
    print()

    init_retina_scale()
    screenshot = take_screenshot()

    elements = config.get("elements", {})
    found = 0
    total = 0
    confidence = config.get("settings", {}).get("confidence", 0.85)

    def test_element(name: str, filename: str):
        nonlocal found, total
        total += 1
        filepath = asset_dir / filename
        if not filepath.exists():
            print(f"  [ MISSING ] {name}: file not found ({filepath})")
            return

        pos = find_element(str(filepath), confidence, screenshot=screenshot)
        if pos:
            print(f"  [  FOUND  ] {name} at ({pos[0]}, {pos[1]})")
            found += 1
        else:
            print(f"  [NOT FOUND] {name}")

    for key, value in elements.items():
        if isinstance(value, str):
            test_element(key, value)
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                test_element(f"{key}.{sub_key}", sub_value)

    print(f"\n  Result: {found}/{total} elements found on screen")


def main():
    parser = argparse.ArgumentParser(
        description="Capture game assets and generate YAML configs"
    )
    parser.add_argument(
        "--game", required=True, help="Game name (used for directory and config naming)"
    )
    parser.add_argument(
        "--type",
        choices=["slot", "crazy_time"],
        help="Game type (slot or crazy_time)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: verify all assets can be found on screen",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all screenshots and config for a game, then re-capture",
    )

    args = parser.parse_args()

    init_retina_scale()

    if args.reset:
        reset_game(args.game)
        if not args.type:
            print("  Add --type slot or --type crazy_time to re-capture now.")
            sys.exit(0)
        captured = capture_elements(args.game, args.type)
        config_path = generate_yaml_config(args.game, args.type, captured)
        print(f"\n{'='*60}")
        print(f"  Re-captured! Config: {config_path}")
        print(f"  Run: python3 main.py --config {config_path} --duration 60")
        print(f"{'='*60}\n")
    elif args.test:
        test_assets(args.game)
    else:
        if not args.type:
            print("Error: --type is required when capturing (not in --test mode)")
            sys.exit(1)

        captured = capture_elements(args.game, args.type)
        config_path = generate_yaml_config(args.game, args.type, captured)

        print(f"\n{'='*60}")
        print(f"  Done! Next steps:")
        print(f"  1. Review config: {config_path}")
        print(f"  2. Adjust bet amounts in the YAML")
        print(f"  3. Test: python3 tools/capture.py --game {args.game} --test")
        print(f"  4. Run: python3 main.py --config {config_path} --duration 60")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
