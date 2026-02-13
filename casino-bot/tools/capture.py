#!/usr/bin/env python3
"""
Asset capture tool for setting up new games.

Usage:
  # See what assets are needed for a game type
  python3 tools/capture.py --help-game infinite_blackjack

  # Capture all assets for a new game (type auto-detected from name)
  python3 tools/capture.py --game infinite_blackjack_fd
  python3 tools/capture.py --game crazy_time_dk
  python3 tools/capture.py --game my_slot_dk --type slot

  # Re-capture (or add) a single asset without re-running full capture
  python3 tools/capture.py --game diamond_wild --update-asset dismiss_popup
  python3 tools/capture.py --game my_slot_dk --update-asset spin_button

  # Test if all assets for a game can be found on screen
  python3 tools/capture.py --game my_slot_dk --test

  # Reset and re-capture everything
  python3 tools/capture.py --game my_slot_dk --reset

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

# ── Common optional elements (shared across all game types) ──────────────
COMMON_OPTIONAL_ELEMENTS = [
    ("reality_check", "Reality check popup button (the button to dismiss the popup)"),
]

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

DIAMOND_WILD_ELEMENTS = [
    ("spin_button", "Spin button (the button to start a spin)", True),
]

DIAMOND_WILD_OPTIONAL_ELEMENTS = [
    ("dismiss_popup", "Popup screen that needs clicking anywhere to dismiss"),
]

DIAMOND_WILD_REGIONS = []

SLOT_REGIONS = [
    ("balance", "Balance display area (the number showing your balance)"),
    ("bet_amount", "Bet amount display area (shows current bet per spin)"),
]

CRAZY_TIME_REGIONS = [
    ("balance", "Balance display area"),
]

INFINITE_BLACKJACK_ELEMENTS = [
    ("betting_open", '"PLACE YOUR BETS" text (visible during betting phase)', True),
    ("hit_button", "HIT button with + icon (visible during decision phase)", True),
    ("stand_button", "STAND button with - icon (visible during decision phase)", True),
    ("double_button", "DOUBLE button (visible during decision phase)", True),
    ("chip_1", "$1 chip in the chip tray (visible during betting phase)", True),
]

INFINITE_BLACKJACK_OPTIONAL_ELEMENTS = [
    ("repeat_button", "REPEAT button (appears after first bet is placed)"),
]

INFINITE_BLACKJACK_REGIONS = [
    ("player_total", "Green circle showing player hand total (near player cards)"),
    ("dealer_upcard", "Label showing dealer visible card value (near dealer card)"),
    ("balance", "Balance amount display (bottom of screen)"),
]

INFINITE_BLACKJACK_POSITIONS = [
    ("bet_spot", "Main betting area on the table (where to place chip)"),
]

# ── Game type registry ───────────────────────────────────────────────────
# Maps game type to its element, optional element, region, and position lists.

GAME_TYPE_DEFS = {
    "slot": {
        "elements": SLOT_ELEMENTS,
        "optional_elements": SLOT_OPTIONAL_ELEMENTS,
        "regions": SLOT_REGIONS,
        "positions": [],
    },
    "crazy_time": {
        "elements": CRAZY_TIME_ELEMENTS,
        "optional_elements": CRAZY_TIME_OPTIONAL_ELEMENTS,
        "regions": CRAZY_TIME_REGIONS,
        "positions": [("1", "Hover over the '1' bet area")],
    },
    "diamond_wild": {
        "elements": DIAMOND_WILD_ELEMENTS,
        "optional_elements": DIAMOND_WILD_OPTIONAL_ELEMENTS,
        "regions": DIAMOND_WILD_REGIONS,
        "positions": [],
    },
    "infinite_blackjack": {
        "elements": INFINITE_BLACKJACK_ELEMENTS,
        "optional_elements": INFINITE_BLACKJACK_OPTIONAL_ELEMENTS,
        "regions": INFINITE_BLACKJACK_REGIONS,
        "positions": INFINITE_BLACKJACK_POSITIONS,
    },
}

KNOWN_GAME_TYPES = list(GAME_TYPE_DEFS.keys())


def detect_game_type(game_name: str) -> str | None:
    """
    Auto-detect game type from game name by matching against known types.

    Checks if the game name starts with a known type. Uses longest match
    to avoid ambiguity (e.g. 'diamond_wild' before 'diamond').

    Returns:
        Matched game type string, or None if no match found.
    """
    # Sort by length descending so longer types match first
    sorted_types = sorted(KNOWN_GAME_TYPES, key=len, reverse=True)
    for game_type in sorted_types:
        if game_name == game_type or game_name.startswith(game_type + "_"):
            return game_type
    return None


def print_game_help(game_type: str) -> None:
    """Print a full checklist of assets needed for a game type."""
    defs = GAME_TYPE_DEFS.get(game_type)
    if defs is None:
        print(f"\n  Unknown game type: '{game_type}'")
        print(f"  Available types: {', '.join(KNOWN_GAME_TYPES)}\n")
        sys.exit(1)

    elements = defs["elements"]
    optional_elements = defs["optional_elements"]
    regions = defs["regions"]
    positions = defs["positions"]

    # Counts
    n_required_templates = len(elements)
    n_optional_templates = len(optional_elements) + len(COMMON_OPTIONAL_ELEMENTS)
    n_regions = len(regions)
    n_positions = len(positions)

    print(f"\n  Assets needed for: {game_type}")
    print(f"  {'=' * 40}")

    if elements or optional_elements or COMMON_OPTIONAL_ELEMENTS:
        print(f"\n  TEMPLATE IMAGES (screenshot a UI element):")
        for name, desc, *_ in elements:
            print(f"    [required]  {name:<20s} {desc}")
        for name, desc in optional_elements:
            print(f"    [optional]  {name:<20s} {desc}")
        for name, desc in COMMON_OPTIONAL_ELEMENTS:
            print(f"    [optional]  {name:<20s} {desc}")

    if regions:
        print(f"\n  OCR REGIONS (draw a box around a number):")
        for name, desc in regions:
            print(f"    [required]  {name:<20s} {desc}")

    if positions:
        print(f"\n  CLICK POSITIONS (hover and press Enter):")
        for name, desc in positions:
            print(f"    [required]  {name:<20s} {desc}")

    print(f"\n  Total: {n_required_templates} required templates, "
          f"{n_optional_templates} optional templates, "
          f"{n_regions} regions, {n_positions} positions\n")


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

    defs = GAME_TYPE_DEFS.get(game_type)
    if defs is None:
        print(f"Unknown game type: {game_type}")
        print(f"Available types: {', '.join(KNOWN_GAME_TYPES)}")
        sys.exit(1)

    required_elements = defs["elements"]
    optional_elements = defs["optional_elements"]
    regions_list = defs["regions"]
    positions_list = defs["positions"]

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

    # ── Step 2: Optional elements (game-specific + common) ──
    all_optional = list(optional_elements) + COMMON_OPTIONAL_ELEMENTS
    if all_optional:
        print(f"\n--- Optional Elements ({len(all_optional)}) ---\n")
        for elem_name, description in all_optional:
            answer = input(f"  [{elem_name}] {description}\n    Capture this? (y/n): ").strip().lower()
            if answer != "y":
                print("    Skipped.\n")
                continue

            result = capture_screenshot_region()
            if result is None:
                print("    Failed — try again")
                result = capture_screenshot_region()
            if result is None:
                print("    Skipped.\n")
                continue

            img, region = result
            filename = f"{elem_name}.png"
            filepath = asset_dir / filename
            cv2.imwrite(str(filepath), img)
            captured_elements[elem_name] = filename
            print(f"    Saved: {filepath}\n")

    # ── Step 3: OCR Regions ──
    if regions_list:
        print(f"\n--- OCR Regions ({len(regions_list)}) ---\n")
        print("  For each region, select the area containing the number to read.\n")
        for region_name, description in regions_list:
            print(f"  [{region_name}] {description}")
            result = capture_screenshot_region()
            if result is None:
                print("    Failed — try again")
                result = capture_screenshot_region()
            if result is None:
                print("    Skipped.\n")
                continue

            _, region = result
            captured_regions[region_name] = region
            print(f"    Region: x={region['x']}, y={region['y']}, "
                  f"w={region['w']}, h={region['h']}\n")

    # ── Step 4: Click positions ──
    if positions_list:
        print(f"\n--- Click Positions ({len(positions_list)}) ---\n")
        for pos_name, description in positions_list:
            pos = capture_position(f"[{pos_name}] {description} — hover and press Enter")
            captured_positions[pos_name] = {"x": pos[0], "y": pos[1]}
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

    config_generators = {
        "slot": _generate_slot_config,
        "crazy_time": _generate_crazy_time_config,
        "diamond_wild": _generate_diamond_wild_config,
        "infinite_blackjack": _generate_infinite_blackjack_config,
    }

    generator = config_generators.get(game_type)
    if generator:
        config = generator(game_name, captured)
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


def _generate_diamond_wild_config(game_name: str, captured: dict) -> dict:
    """Generate Diamond Wild YAML config."""
    return {
        "game": {
            "name": game_name.replace("_", " ").title(),
            "type": "diamond_wild",
            "platform": "draftkings",
            "asset_dir": captured.get("asset_dir", f"assets/{game_name}/"),
        },
        "elements": captured.get("elements", {}),
        "regions": captured.get("regions", {}),
        "settings": {
            "confidence": 0.85,
            "action_delay": [0.3, 0.8],
            "spin_wait": 1.0,
            "poll_interval": 1.0,
            "session_duration": 60,
        },
    }


def _generate_infinite_blackjack_config(game_name: str, captured: dict) -> dict:
    """Generate Infinite Blackjack YAML config."""
    elements = captured.get("elements", {})
    positions = captured.get("positions", {})

    # Extract bet_spot position
    bet_spot = positions.get("bet_spot", {"x": 0, "y": 0})

    return {
        "game": {
            "name": game_name.replace("_", " ").title(),
            "type": "infinite_blackjack",
            "platform": "fanduel",
            "asset_dir": captured.get("asset_dir", f"assets/{game_name}/"),
        },
        "elements": elements,
        "regions": captured.get("regions", {}),
        "bet_spot": bet_spot,
        "settings": {
            "confidence": 0.80,
            "action_delay": [0.2, 0.5],
            "poll_interval": 1.0,
            "session_duration": 60,
        },
    }


def update_single_asset(game_name: str, element_name: str) -> None:
    """Re-capture a single asset for an existing game."""
    asset_dir = PROJECT_ROOT / "assets" / game_name
    config_path = PROJECT_ROOT / "config" / "games" / f"{game_name}.yaml"

    if not config_path.exists():
        print(f"Config not found: {config_path}")
        print(f"Run a full capture first: python3 tools/capture.py --game {game_name} --type <type>")
        sys.exit(1)

    asset_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Updating asset '{element_name}' for: {game_name}")
    print(f"{'='*60}")
    print()
    print("  Make sure the game is open and visible in Chrome.")
    print()

    print(f"  [{element_name}] Select the region for this element")
    result = capture_screenshot_region()
    if result is None:
        print("    Failed — try again")
        result = capture_screenshot_region()
    if result is None:
        print("    Cancelled.\n")
        sys.exit(1)

    img, region = result
    filename = f"{element_name}.png"
    filepath = asset_dir / filename
    cv2.imwrite(str(filepath), img)
    print(f"    Saved: {filepath}")

    # Update the YAML config to include this element if it's not already there
    with open(config_path) as f:
        config = yaml.safe_load(f)

    elements = config.get("elements", {})
    if element_name not in elements:
        elements[element_name] = filename
        config["elements"] = elements

    # For reality_check, also capture where to click to dismiss
    if element_name == "reality_check":
        print()
        pos = capture_position("Hover over the BUTTON to dismiss the reality check, press Enter")
        settings = config.get("settings", {})
        settings["reality_check_click"] = {"x": pos[0], "y": pos[1]}
        config["settings"] = settings
        print(f"    Click position set to: ({pos[0]}, {pos[1]})")

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    print(f"    Config updated: {config_path}")

    print(f"\n  Done! Test with: python3 tools/capture.py --game {game_name} --test\n")


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


def _resolve_game_type(args) -> str | None:
    """Resolve game type from --type flag or auto-detect from game name."""
    if args.type:
        return args.type

    detected = detect_game_type(args.game)
    if detected:
        print(f"  Auto-detected game type: {detected}")
        return detected

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Capture game assets and generate YAML configs"
    )
    parser.add_argument(
        "--game", help="Game name (used for directory and config naming)"
    )
    parser.add_argument(
        "--type",
        choices=KNOWN_GAME_TYPES,
        help="Game type (auto-detected from game name if omitted)",
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
    parser.add_argument(
        "--update-asset",
        metavar="ELEMENT",
        help="Re-capture a single asset by name (e.g. --update-asset dismiss_popup)",
    )
    parser.add_argument(
        "--help-game",
        metavar="TYPE",
        help="Print a checklist of all assets needed for a game type",
    )

    args = parser.parse_args()

    # --help-game doesn't require --game
    if args.help_game:
        print_game_help(args.help_game)
        sys.exit(0)

    # All other commands require --game
    if not args.game:
        parser.error("--game is required (unless using --help-game)")

    init_retina_scale()

    if args.update_asset:
        update_single_asset(args.game, args.update_asset)
    elif args.reset:
        game_type = _resolve_game_type(args)
        reset_game(args.game)
        if not game_type:
            print(f"  Add --type <type> to re-capture now.")
            print(f"  Available types: {', '.join(KNOWN_GAME_TYPES)}")
            sys.exit(0)
        captured = capture_elements(args.game, game_type)
        config_path = generate_yaml_config(args.game, game_type, captured)
        print(f"\n{'='*60}")
        print(f"  Re-captured! Config: {config_path}")
        print(f"  Run: python3 main.py --config {config_path} --duration 60")
        print(f"{'='*60}\n")
    elif args.test:
        test_assets(args.game)
    else:
        game_type = _resolve_game_type(args)
        if not game_type:
            print(f"Error: Could not auto-detect game type from '{args.game}'.")
            print(f"  Use --type <type> to specify it explicitly.")
            print(f"  Available types: {', '.join(KNOWN_GAME_TYPES)}")
            sys.exit(1)

        captured = capture_elements(args.game, game_type)
        config_path = generate_yaml_config(args.game, game_type, captured)

        print(f"\n{'='*60}")
        print(f"  Done! Next steps:")
        print(f"  1. Review config: {config_path}")
        print(f"  2. Test: python3 tools/capture.py --game {args.game} --test")
        print(f"  3. Run: python3 main.py --config {config_path} --duration 60")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
