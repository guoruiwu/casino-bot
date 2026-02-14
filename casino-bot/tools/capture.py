#!/usr/bin/env python3
"""
Asset capture tool for setting up new games.

Usage:
  # Interactive mode (arrow-key menus to select game and assets)
  python3 tools/capture.py

  # See what assets are needed for a game
  python3 tools/capture.py --help-game infinite_blackjack

  # Capture all assets for a game
  python3 tools/capture.py --game infinite_blackjack
  python3 tools/capture.py --game crazy_time
  python3 tools/capture.py --game slot

  # Re-capture assets interactively (arrow-key picker)
  python3 tools/capture.py --game diamond_wild --update-asset

  # Re-capture a single asset by name
  python3 tools/capture.py --game diamond_wild --update-asset dismiss_popup
  python3 tools/capture.py --game slot --update-asset spin_button

  # Test if all assets for a game can be found on screen
  python3 tools/capture.py --game slot --test

  # Reset and re-capture everything
  python3 tools/capture.py --game slot --reset

  # Snapshot mode: screenshot each game state first, then crop from frozen images
  # (recommended for live-dealer games like Infinite Blackjack)
  python3 tools/capture.py --game infinite_blackjack --snapshot

How it works:
  1. Takes a screenshot of your current screen
  2. For each required element, you position your mouse on the corners and press Enter
  3. Saves cropped PNGs and generates a starter YAML config

  Snapshot mode (--snapshot):
  1. Prompts you to get the game into each required state, takes a screenshot of each
  2. Opens a Tkinter window where you draw rectangles to crop assets from frozen images
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
import pytesseract
import yaml
from InquirerPy import inquirer
from InquirerPy.separator import Separator

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.screen import find_element, init_retina_scale, take_screenshot

# Set up tesseract path (same logic as src/screen.py)
import shutil

_tesseract_path = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract"
if Path(_tesseract_path).exists():
    pytesseract.pytesseract.tesseract_cmd = _tesseract_path


def _ocr_preview(crop_2x: np.ndarray, preprocess: str = "thresh") -> str:
    """Run OCR on a cropped 2x region and return the recognized text."""
    gray = cv2.cvtColor(crop_2x, cv2.COLOR_BGR2GRAY)
    if preprocess == "thresh":
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    elif preprocess == "blur":
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
    scale = 2
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    text = pytesseract.image_to_string(gray, config="--psm 7")
    return text.strip()


# ── Common optional elements (shared across all games) ───────────────────
COMMON_OPTIONAL_ELEMENTS = [
    ("reality_check", "Reality check popup button (the button to dismiss the popup)"),
]

# ── Element definitions per game ─────────────────────────────────────────
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
    ("chip_tray", "Chip tray (visible during betting phase)", True),
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
    ("dealer_total", "Dealer total display (shows dealer hand value)"),
    ("balance", "Balance amount display (bottom of screen)"),
]

INFINITE_BLACKJACK_POSITIONS = [
    ("bet_spot", "Main betting area on the table (where to place chip)"),
]

# ── Game registry ────────────────────────────────────────────────────────
# Maps game to its element, optional element, region, and position lists.

GAME_DEFS = {
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

KNOWN_GAMES = list(GAME_DEFS.keys())

# ── State groups for snapshot capture mode ────────────────────────────────
# Maps games (with multiple live states) to a list of state groups.
# Each group describes one game state that the user needs to screenshot,
# and which elements/regions/positions belong to that state.
# Games not listed here don't need snapshot mode (e.g. slots).

GAME_STATE_GROUPS: dict[str, list[dict]] = {
    "infinite_blackjack": [
        {
            "state": "Betting Phase",
            "hint": "Wait for 'PLACE YOUR BETS' to appear, then press Enter.",
            "elements": ["chip_tray", "chip_1"],
            "optional_elements": ["repeat_button"],
            "regions": ["balance"],
            "positions": ["bet_spot"],
        },
        {
            "state": "Decision Phase",
            "hint": "Wait for HIT/STAND buttons to appear, then press Enter.",
            "elements": ["hit_button", "stand_button", "double_button"],
            "optional_elements": [],
            "regions": ["player_total", "dealer_total"],
            "positions": [],
        },
    ],
}


def print_game_help(game: str) -> None:
    """Print a full checklist of assets needed for a game."""
    defs = GAME_DEFS.get(game)
    if defs is None:
        print(f"\n  Unknown game: '{game}'")
        print(f"  Available games: {', '.join(KNOWN_GAMES)}\n")
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

    print(f"\n  Assets needed for: {game}")
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


def reset_game(game: str) -> None:
    """Delete all screenshots and config for a game."""
    import shutil

    asset_dir = PROJECT_ROOT / "assets" / game
    config_path = PROJECT_ROOT / "config" / "games" / f"{game}.yaml"

    deleted = []
    if asset_dir.exists():
        shutil.rmtree(asset_dir)
        deleted.append(str(asset_dir))
    if config_path.exists():
        config_path.unlink()
        deleted.append(str(config_path))

    if deleted:
        print(f"\n  Reset '{game}' — deleted:")
        for d in deleted:
            print(f"    {d}")
        print()
    else:
        print(f"\n  Nothing to reset for '{game}'.\n")


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


def capture_elements(game: str) -> dict:
    """Walk through capturing elements for a game — only the essentials."""
    asset_dir = PROJECT_ROOT / "assets" / game
    asset_dir.mkdir(parents=True, exist_ok=True)

    defs = GAME_DEFS[game]

    required_elements = defs["elements"]
    optional_elements = defs["optional_elements"]
    regions_list = defs["regions"]
    positions_list = defs["positions"]

    captured_elements = {}
    captured_regions = {}
    captured_positions = {}

    print(f"\n{'='*60}")
    print(f"  Capturing assets for: {game}")
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

            img, region = result
            captured_regions[region_name] = region
            print(f"    Region: x={region['x']}, y={region['y']}, "
                  f"w={region['w']}, h={region['h']}")
            # Show OCR preview
            try:
                preview = _ocr_preview(img)
                print(f'    OCR preview: "{preview}"')
            except Exception:
                print("    OCR preview: <failed>")
            print()

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
        "asset_dir": f"assets/{game}/",
    }


def generate_yaml_config(game: str, captured: dict) -> str:
    """Generate a YAML config file from captured data."""
    config_dir = PROJECT_ROOT / "config" / "games"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / f"{game}.yaml"

    config_generators = {
        "slot": _generate_slot_config,
        "crazy_time": _generate_crazy_time_config,
        "diamond_wild": _generate_diamond_wild_config,
        "infinite_blackjack": _generate_infinite_blackjack_config,
    }

    generator = config_generators.get(game)
    if generator:
        config = generator(game, captured)
    else:
        config = {}

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"\n  Config saved: {config_path}")
    return str(config_path)


def _generate_slot_config(game: str, captured: dict) -> dict:
    """Generate slot YAML config."""
    return {
        "game": {
            "name": game.replace("_", " ").title(),
            "platform": "draftkings",
            "asset_dir": captured.get("asset_dir", f"assets/{game}/"),
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


def _generate_crazy_time_config(game: str, captured: dict) -> dict:
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
            "name": game.replace("_", " ").title(),
            "platform": "draftkings",
            "asset_dir": captured.get("asset_dir", f"assets/{game}/"),
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


def _generate_diamond_wild_config(game: str, captured: dict) -> dict:
    """Generate Diamond Wild YAML config."""
    return {
        "game": {
            "name": game.replace("_", " ").title(),
            "platform": "draftkings",
            "asset_dir": captured.get("asset_dir", f"assets/{game}/"),
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


def _generate_infinite_blackjack_config(game: str, captured: dict) -> dict:
    """Generate Infinite Blackjack YAML config."""
    elements = captured.get("elements", {})
    positions = captured.get("positions", {})

    # Extract bet_spot position
    bet_spot = positions.get("bet_spot", {"x": 0, "y": 0})

    return {
        "game": {
            "name": game.replace("_", " ").title(),
            "platform": "fanduel",
            "asset_dir": captured.get("asset_dir", f"assets/{game}/"),
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


def update_single_asset(game: str, element_name: str) -> None:
    """Re-capture a single asset for an existing game."""
    asset_dir = PROJECT_ROOT / "assets" / game
    config_path = PROJECT_ROOT / "config" / "games" / f"{game}.yaml"

    if not config_path.exists():
        print(f"Config not found: {config_path}")
        print(f"Run a full capture first: python3 tools/capture.py --game {game}")
        sys.exit(1)

    asset_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Updating asset '{element_name}' for: {game}")
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

    print(f"\n  Done! Test with: python3 tools/capture.py --game {game} --test\n")


def test_assets(game: str) -> None:
    """Test if all captured assets can be found on the current screen."""
    asset_dir = PROJECT_ROOT / "assets" / game
    config_dir = PROJECT_ROOT / "config" / "games"

    config_path = config_dir / f"{game}.yaml"
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    print(f"\n{'='*60}")
    print(f"  Testing assets for: {game}")
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


# ── Snapshot capture mode ─────────────────────────────────────────────────
# Takes screenshots of each game state first, then lets the user crop
# assets from frozen images using a Tkinter GUI overlay.


class RegionSelector:
    """
    OpenCV-based GUI for selecting regions/positions from a screenshot image.

    Displays the screenshot and lets the user:
      - Draw rectangles (click-and-drag) to select template elements or OCR regions
      - Single-click to select click positions
      - Press 's' to skip the current element
      - Press 'u' to undo the last selection
      - Press 'q' or Escape to finish/quit
    """

    WINDOW_NAME = "Snapshot Capture — Region Selector"

    def __init__(
        self,
        screenshot_2x: np.ndarray,
        tasks: list[dict],
        asset_dir: Path,
    ):
        """
        Args:
            screenshot_2x: Full-resolution (2x Retina) screenshot as BGR numpy array.
            tasks: List of dicts, each with keys:
                - name: str (element name)
                - description: str
                - category: "element" | "region" | "position"
            asset_dir: Directory to save cropped element PNGs.
        """
        self.screenshot_2x = screenshot_2x
        self.tasks = list(tasks)
        self.asset_dir = asset_dir

        self.results: dict[str, dict] = {}  # name -> result data
        self.task_idx = 0

        # Display at 1x logical size (half of Retina 2x)
        h_2x, w_2x = screenshot_2x.shape[:2]
        self.display_w = w_2x // 2
        self.display_h = h_2x // 2
        self.scale = 2  # display-to-image scale factor

        # Prepare the 1x display image
        self.base_display = cv2.resize(
            screenshot_2x,
            (self.display_w, self.display_h),
            interpolation=cv2.INTER_AREA,
        )

        # Drawing state
        self._drawing = False
        self._start_x: int = 0
        self._start_y: int = 0
        self._current_x: int = 0
        self._current_y: int = 0

        # Overlay history: list of (type, data) for drawn markers
        self._overlays: list[tuple[str, tuple]] = []

        # OCR preview text (shown after capturing a region)
        self._ocr_preview_text: str | None = None

    def run(self) -> dict[str, dict]:
        """Run the selector and return results when all tasks are done."""
        cv2.namedWindow(self.WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.WINDOW_NAME, self._mouse_callback)

        self._redraw()

        while True:
            key = cv2.waitKey(30) & 0xFF

            if key == ord("s"):
                # Skip current task
                self._on_skip()
            elif key == ord("u"):
                # Undo last selection
                self._on_undo()
            elif key == ord("q") or key == 27:  # q or Escape
                break

            # Check if all tasks are done — wait for explicit confirmation
            if self.task_idx >= len(self.tasks):
                self._redraw()
                confirmed = self._wait_for_confirmation()
                if confirmed:
                    break  # exit outer loop

        cv2.destroyWindow(self.WINDOW_NAME)
        return self.results

    # ── Drawing ──────────────────────────────────────────────────────────

    def _redraw(self) -> None:
        """Redraw the display image with overlays and prompt text."""
        display = self.base_display.copy()

        # Draw all committed overlays
        for kind, data in self._overlays:
            if kind == "rect":
                x1, y1, x2, y2 = data
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 0, 255), 2)
            elif kind == "point":
                cx, cy = data
                cv2.circle(display, (cx, cy), 6, (0, 0, 255), 2)

        # Draw in-progress rectangle
        if self._drawing:
            x1 = min(self._start_x, self._current_x)
            y1 = min(self._start_y, self._current_y)
            x2 = max(self._start_x, self._current_x)
            y2 = max(self._start_y, self._current_y)
            cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # Draw prompt bar at the top
        task = self._current_task()
        if task is None:
            prompt = "All done! Press Enter/Space to confirm, or 'u' to undo."
        else:
            n = self.task_idx + 1
            total = len(self.tasks)
            if task["category"] == "position":
                action = "CLICK on"
            else:
                action = "DRAW rectangle around"
            prompt = (
                f"({n}/{total}) {action}: {task['name']} — {task['description']}  "
                f"[s=skip, u=undo, q=quit]"
            )

        # Draw a dark banner at the top for readability
        banner_h = 40
        if self._ocr_preview_text is not None:
            banner_h = 70  # taller banner to fit OCR preview line
        cv2.rectangle(display, (0, 0), (self.display_w, banner_h), (30, 30, 30), -1)
        # Truncate prompt if too long for display
        cv2.putText(
            display,
            prompt,
            (10, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

        # Draw OCR preview text on a second line if available
        if self._ocr_preview_text is not None:
            ocr_label = f'OCR preview: "{self._ocr_preview_text}"'
            cv2.putText(
                display,
                ocr_label,
                (10, 56),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 200),  # cyan-green for visibility
                1,
                cv2.LINE_AA,
            )

        cv2.imshow(self.WINDOW_NAME, display)

    # ── Task navigation ──────────────────────────────────────────────────

    def _current_task(self) -> dict | None:
        if self.task_idx < len(self.tasks):
            return self.tasks[self.task_idx]
        return None

    def _is_position_mode(self) -> bool:
        task = self._current_task()
        return task is not None and task["category"] == "position"

    def _advance(self) -> None:
        """Move to the next task."""
        self.task_idx += 1
        self._drawing = False
        self._redraw()

    # ── Mouse callback ───────────────────────────────────────────────────

    def _mouse_callback(self, event, x, y, flags, param) -> None:
        task = self._current_task()
        if task is None:
            return

        if self._is_position_mode():
            # Single click — record position on mouse-up
            if event == cv2.EVENT_LBUTTONDOWN:
                self.results[task["name"]] = {
                    "category": "position",
                    "x": x,
                    "y": y,
                }
                self._overlays.append(("point", (x, y)))
                self._advance()
            return

        # Rectangle mode
        if event == cv2.EVENT_LBUTTONDOWN:
            self._drawing = True
            self._start_x = x
            self._start_y = y
            self._current_x = x
            self._current_y = y

        elif event == cv2.EVENT_MOUSEMOVE and self._drawing:
            self._current_x = x
            self._current_y = y
            self._redraw()

        elif event == cv2.EVENT_LBUTTONUP and self._drawing:
            self._drawing = False
            self._ocr_preview_text = None  # clear previous OCR preview
            x1 = min(self._start_x, x)
            y1 = min(self._start_y, y)
            x2 = max(self._start_x, x)
            y2 = max(self._start_y, y)

            # Reject tiny selections
            if (x2 - x1) < 4 or (y2 - y1) < 4:
                self._redraw()
                return

            # Crop from the full-res 2x image
            s = self.scale
            crop = self.screenshot_2x[y1 * s : y2 * s, x1 * s : x2 * s]

            if task["category"] == "element":
                filename = f"{task['name']}.png"
                filepath = self.asset_dir / filename
                cv2.imwrite(str(filepath), crop)
                self.results[task["name"]] = {
                    "category": "element",
                    "filename": filename,
                }
            elif task["category"] == "region":
                self.results[task["name"]] = {
                    "category": "region",
                    "x": x1,
                    "y": y1,
                    "w": x2 - x1,
                    "h": y2 - y1,
                }
                # Run OCR on the cropped region and show preview
                try:
                    self._ocr_preview_text = _ocr_preview(crop)
                except Exception:
                    self._ocr_preview_text = "<OCR failed>"

            self._overlays.append(("rect", (x1, y1, x2, y2)))
            self._advance()

    # ── Button handlers ──────────────────────────────────────────────────

    def _on_skip(self) -> None:
        if self._current_task() is not None:
            self._overlays.append(("skip", ()))  # placeholder for undo tracking
            self._advance()

    def _on_undo(self) -> None:
        if self.task_idx == 0:
            return
        # Go back one step
        self.task_idx -= 1
        self._drawing = False
        task = self._current_task()
        if task and task["name"] in self.results:
            del self.results[task["name"]]
        # Remove last overlay
        if self._overlays:
            self._overlays.pop()
        self._redraw()

    def _wait_for_confirmation(self) -> bool:
        """
        Block until the user confirms (Enter/Space/q/Escape) or undoes.

        Returns:
            True if the user confirmed (should exit).
            False if the user pressed undo (caller should continue the loop).
        """
        while True:
            key = cv2.waitKey(30) & 0xFF
            if key == ord("u"):
                self._on_undo()
                return False  # go back to main loop
            if key in (13, 32, ord("q"), 27):
                # Enter, Space, q, or Escape — confirmed
                return True


def _build_task_list(
    game: str,
    selected_names: set[str] | None = None,
) -> list[dict]:
    """
    Build an ordered list of tasks for the RegionSelector from GAME_DEFS.

    If *selected_names* is provided, only include tasks whose name is in the set.
    Returns a list of dicts with keys: name, description, category.
    """
    defs = GAME_DEFS[game]

    # Build description lookups
    elem_desc: dict[str, str] = {}
    for name, desc, *_ in defs["elements"]:
        elem_desc[name] = desc
    for name, desc in defs["optional_elements"]:
        elem_desc[name] = desc
    for name, desc in COMMON_OPTIONAL_ELEMENTS:
        elem_desc[name] = desc

    region_desc = {name: desc for name, desc in defs["regions"]}
    position_desc = {name: desc for name, desc in defs["positions"]}

    tasks: list[dict] = []

    # Elements
    for name, desc, *_ in defs["elements"]:
        if selected_names is None or name in selected_names:
            tasks.append({"name": name, "description": desc, "category": "element"})
    for name, desc in defs["optional_elements"]:
        if selected_names is not None and name in selected_names:
            tasks.append({"name": name, "description": desc, "category": "element"})
    for name, desc in COMMON_OPTIONAL_ELEMENTS:
        if selected_names is not None and name in selected_names:
            tasks.append({"name": name, "description": desc, "category": "element"})

    # Regions
    for name, desc in defs["regions"]:
        if selected_names is None or name in selected_names:
            tasks.append({"name": name, "description": desc, "category": "region"})

    # Positions
    for name, desc in defs["positions"]:
        if selected_names is None or name in selected_names:
            tasks.append({"name": name, "description": desc, "category": "position"})

    return tasks


def _collect_snapshots(
    game: str,
    state_groups: list[dict],
    needed_names: set[str] | None = None,
) -> dict[str, np.ndarray]:
    """
    Phase 1: Prompt the user to get the game into each required state and
    take a screenshot for each one.

    Args:
        game: Game key.
        state_groups: The GAME_STATE_GROUPS list for this game.
        needed_names: If provided, only collect snapshots for states that
                      contain at least one needed asset.

    Returns:
        Dict mapping state name -> 2x Retina screenshot (BGR numpy array).
    """
    # Filter to only states that contain needed assets
    if needed_names is not None:
        filtered = []
        for group in state_groups:
            all_names = (
                group.get("elements", [])
                + group.get("optional_elements", [])
                + group.get("regions", [])
                + group.get("positions", [])
            )
            if any(n in needed_names for n in all_names):
                filtered.append(group)
        state_groups = filtered

    if not state_groups:
        return {}

    print(f"\n{'='*60}")
    print(f"  Snapshot mode for: {game}")
    print(f"{'='*60}")
    print()
    print("  You need screenshots from these game states:")
    for i, group in enumerate(state_groups, 1):
        all_names = (
            group.get("elements", [])
            + group.get("optional_elements", [])
            + group.get("regions", [])
            + group.get("positions", [])
        )
        # Filter to only needed names if applicable
        if needed_names is not None:
            all_names = [n for n in all_names if n in needed_names]
        names_str = ", ".join(all_names)
        print(f"    {i}. {group['state']}  — {names_str}")
    print()
    print("  Make sure the game is open and visible in Chrome.")
    print()

    snapshots: dict[str, np.ndarray] = {}

    for i, group in enumerate(state_groups, 1):
        state_name = group["state"]
        hint = group.get("hint", "Press Enter to take a screenshot.")
        print(f"  Step {i}/{len(state_groups)}: {state_name}")
        print(f"    {hint}")
        input("    > ")

        screenshot = take_screenshot()
        snapshots[state_name] = screenshot

        # Persist snapshot to disk so it can be reused by --redraw-regions
        snapshot_dir = PROJECT_ROOT / "assets" / game
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        safe_name = state_name.lower().replace(" ", "_")
        snapshot_path = snapshot_dir / f"_snapshot_{safe_name}.png"
        cv2.imwrite(str(snapshot_path), screenshot)

        print(f"    Screenshot captured for: {state_name}")
        print(f"    Saved snapshot: {snapshot_path}")
        print()

    print("  All snapshots collected!\n")
    return snapshots


def _tasks_for_state(
    game: str,
    state_group: dict,
    selected_names: set[str] | None = None,
) -> list[dict]:
    """
    Build RegionSelector task dicts for a single state group.

    Args:
        game: Game key.
        state_group: One entry from GAME_STATE_GROUPS.
        selected_names: If provided, only include tasks whose name is in the set.
    """
    defs = GAME_DEFS[game]

    # Build description lookups
    elem_desc: dict[str, str] = {}
    for name, desc, *_ in defs["elements"]:
        elem_desc[name] = desc
    for name, desc in defs["optional_elements"]:
        elem_desc[name] = desc
    for name, desc in COMMON_OPTIONAL_ELEMENTS:
        elem_desc[name] = desc
    region_desc = {name: desc for name, desc in defs["regions"]}
    position_desc = {name: desc for name, desc in defs["positions"]}

    tasks: list[dict] = []

    for name in state_group.get("elements", []):
        if selected_names is None or name in selected_names:
            desc = elem_desc.get(name, "")
            tasks.append({"name": name, "description": desc, "category": "element"})

    for name in state_group.get("optional_elements", []):
        if selected_names is None or name in selected_names:
            desc = elem_desc.get(name, "")
            tasks.append({"name": name, "description": desc, "category": "element"})

    for name in state_group.get("regions", []):
        if selected_names is None or name in selected_names:
            desc = region_desc.get(name, "")
            tasks.append({"name": name, "description": desc, "category": "region"})

    for name in state_group.get("positions", []):
        if selected_names is None or name in selected_names:
            desc = position_desc.get(name, "")
            tasks.append({"name": name, "description": desc, "category": "position"})

    return tasks


def snapshot_capture(game: str) -> dict:
    """
    Full snapshot capture workflow for a game (CLI mode — captures all assets).

    Phase 1: Collect a screenshot for each game state.
    Phase 2: Open a Tkinter RegionSelector for each screenshot to crop assets.

    Returns:
        Dict with 'elements', 'regions', 'positions', and 'asset_dir' keys
        (same format as capture_elements()).
    """
    state_groups = GAME_STATE_GROUPS.get(game)
    if not state_groups:
        print(f"\n  No state groups defined for '{game}' — falling back to live mode.\n")
        return capture_elements(game)

    asset_dir = PROJECT_ROOT / "assets" / game
    asset_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1: Collect snapshots
    snapshots = _collect_snapshots(game, state_groups)

    # Phase 2: Open RegionSelector for each state's screenshot
    captured_elements: dict[str, str] = {}
    captured_regions: dict[str, dict] = {}
    captured_positions: dict[str, dict] = {}

    for group in state_groups:
        state_name = group["state"]
        screenshot = snapshots.get(state_name)
        if screenshot is None:
            continue

        tasks = _tasks_for_state(game, group)
        if not tasks:
            continue

        print(f"  Opening region selector for: {state_name}")
        print(f"    ({len(tasks)} item(s) to capture)")
        print()

        selector = RegionSelector(screenshot, tasks, asset_dir)
        results = selector.run()

        # Merge results
        for name, data in results.items():
            if data["category"] == "element":
                captured_elements[name] = data["filename"]
            elif data["category"] == "region":
                captured_regions[name] = {
                    "x": data["x"],
                    "y": data["y"],
                    "w": data["w"],
                    "h": data["h"],
                }
            elif data["category"] == "position":
                captured_positions[name] = {
                    "x": data["x"],
                    "y": data["y"],
                }

    return {
        "elements": captured_elements,
        "regions": captured_regions,
        "positions": captured_positions,
        "asset_dir": f"assets/{game}/",
    }


def snapshot_capture_selected(
    game: str,
    selected_assets: list[tuple[str, str]],
) -> dict:
    """
    Snapshot capture workflow for user-selected assets (interactive mode).

    Same as snapshot_capture() but only captures the assets the user
    checked off in the interactive picker.

    Args:
        game: Game key.
        selected_assets: List of (category, name) tuples from interactive_select_assets().

    Returns:
        Dict with 'elements', 'regions', 'positions', and 'asset_dir' keys.
    """
    state_groups = GAME_STATE_GROUPS.get(game)
    if not state_groups:
        print(f"\n  No state groups defined for '{game}' — falling back to live mode.\n")
        return capture_selected_elements(game, selected_assets)

    asset_dir = PROJECT_ROOT / "assets" / game
    asset_dir.mkdir(parents=True, exist_ok=True)

    # Build set of selected names
    needed_names = {name for _cat, name in selected_assets}

    # Phase 1: Collect snapshots (only for states with needed assets)
    snapshots = _collect_snapshots(game, state_groups, needed_names=needed_names)

    # Phase 2: Open RegionSelector for each state's screenshot
    captured_elements: dict[str, str] = {}
    captured_regions: dict[str, dict] = {}
    captured_positions: dict[str, dict] = {}

    for group in state_groups:
        state_name = group["state"]
        screenshot = snapshots.get(state_name)
        if screenshot is None:
            continue

        tasks = _tasks_for_state(game, group, selected_names=needed_names)
        if not tasks:
            continue

        print(f"  Opening region selector for: {state_name}")
        print(f"    ({len(tasks)} item(s) to capture)")
        print()

        selector = RegionSelector(screenshot, tasks, asset_dir)
        results = selector.run()

        # Merge results
        for name, data in results.items():
            if data["category"] == "element":
                captured_elements[name] = data["filename"]
            elif data["category"] == "region":
                captured_regions[name] = {
                    "x": data["x"],
                    "y": data["y"],
                    "w": data["w"],
                    "h": data["h"],
                }
            elif data["category"] == "position":
                captured_positions[name] = {
                    "x": data["x"],
                    "y": data["y"],
                }

    return {
        "elements": captured_elements,
        "regions": captured_regions,
        "positions": captured_positions,
        "asset_dir": f"assets/{game}/",
    }


def redraw_regions(game: str) -> None:
    """
    Re-draw OCR regions on previously saved snapshots without taking new
    screenshots.  Loads cached _snapshot_*.png files from assets/<game>/,
    opens the RegionSelector for region-only tasks, and patches the existing
    YAML config with the new coordinates.
    """
    config_path = PROJECT_ROOT / "config" / "games" / f"{game}.yaml"
    if not config_path.exists():
        print(f"\n  Config not found: {config_path}")
        print(f"  Run a full capture first: python3 tools/capture.py --game {game} --snapshot")
        sys.exit(1)

    state_groups = GAME_STATE_GROUPS.get(game)
    if not state_groups:
        print(f"\n  No state groups defined for '{game}'. --redraw-regions requires snapshot mode.")
        sys.exit(1)

    asset_dir = PROJECT_ROOT / "assets" / game

    # Load cached snapshots from disk
    snapshots: dict[str, np.ndarray] = {}
    missing_states: list[str] = []
    for group in state_groups:
        state_name = group["state"]
        # Only load snapshots for states that have regions
        if not group.get("regions"):
            continue
        safe_name = state_name.lower().replace(" ", "_")
        snapshot_path = asset_dir / f"_snapshot_{safe_name}.png"
        if snapshot_path.exists():
            img = cv2.imread(str(snapshot_path), cv2.IMREAD_COLOR)
            if img is not None:
                snapshots[state_name] = img
            else:
                missing_states.append(state_name)
        else:
            missing_states.append(state_name)

    if missing_states:
        print(f"\n  Missing cached snapshots for: {', '.join(missing_states)}")
        print("  Taking new screenshots for those states...")
        print()
        # Build mini state_groups for just the missing states
        missing_groups = [g for g in state_groups if g["state"] in missing_states]
        fresh = _collect_snapshots(game, missing_groups)
        snapshots.update(fresh)

    if not snapshots:
        print("\n  No states with regions found. Nothing to redraw.")
        return

    print(f"\n{'='*60}")
    print(f"  Redrawing regions for: {game}")
    print(f"{'='*60}")
    print()

    # Phase 2: Open RegionSelector for each state, region tasks only
    new_regions: dict[str, dict] = {}

    for group in state_groups:
        state_name = group["state"]
        screenshot = snapshots.get(state_name)
        if screenshot is None:
            continue

        # Build tasks filtered to regions only
        tasks = _tasks_for_state(game, group)
        region_tasks = [t for t in tasks if t["category"] == "region"]
        if not region_tasks:
            continue

        region_names = ", ".join(t["name"] for t in region_tasks)
        print(f"  Opening region selector for: {state_name}")
        print(f"    Regions to draw: {region_names}")
        print()

        selector = RegionSelector(screenshot, region_tasks, asset_dir)
        results = selector.run()

        for name, data in results.items():
            if data["category"] == "region":
                new_regions[name] = {
                    "x": data["x"],
                    "y": data["y"],
                    "w": data["w"],
                    "h": data["h"],
                }

    if not new_regions:
        print("  No regions were drawn. Config unchanged.")
        return

    # Patch the existing YAML — only update the regions section
    with open(config_path) as f:
        config = yaml.safe_load(f)

    existing_regions = config.get("regions", {})
    existing_regions.update(new_regions)
    config["regions"] = existing_regions

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"\n  Updated regions in: {config_path}")
    for name, coords in new_regions.items():
        print(f"    {name}: x={coords['x']}, y={coords['y']}, "
              f"w={coords['w']}, h={coords['h']}")
    print(f"\n  Done! Test with: python3 tools/capture.py --game {game} --test\n")


# ── Interactive mode functions ────────────────────────────────────────────

# Shared keybindings: arrow keys (default) + vim j/k
VIM_NAV_KEYBINDINGS = {
    "down": [{"key": "down"}, {"key": "j"}],
    "up": [{"key": "up"}, {"key": "k"}],
}

def interactive_select_game() -> str:
    """Arrow-key menu to select a game. First step — no back option."""
    choices = [
        {"name": gt, "value": gt}
        for gt in KNOWN_GAMES
    ]
    return inquirer.select(
        message="Select game:",
        choices=choices,
        keybindings=VIM_NAV_KEYBINDINGS,
    ).execute()


def interactive_select_assets(game: str) -> list[tuple[str, str]]:
    """
    Arrow-key checkbox to select which assets to capture.

    Returns a list of (category, name) tuples where category is one of:
    'element', 'region', 'position'.
    """
    defs = GAME_DEFS[game]
    choices = []

    # Required elements — pre-checked
    if defs["elements"]:
        choices.append(Separator("── Template Images ──"))
        for name, desc, *_ in defs["elements"]:
            choices.append({
                "name": f"[required] {name} — {desc}",
                "value": ("element", name),
                "enabled": True,
            })

    # Optional elements (game-specific + common)
    all_optional = list(defs["optional_elements"]) + COMMON_OPTIONAL_ELEMENTS
    if all_optional:
        choices.append(Separator("── Optional Elements ──"))
        for name, desc in all_optional:
            choices.append({
                "name": f"[optional] {name} — {desc}",
                "value": ("element", name),
                "enabled": False,
            })

    # OCR Regions — pre-checked
    if defs["regions"]:
        choices.append(Separator("── OCR Regions ──"))
        for name, desc in defs["regions"]:
            choices.append({
                "name": f"[region]   {name} — {desc}",
                "value": ("region", name),
                "enabled": True,
            })

    # Click Positions — pre-checked
    if defs["positions"]:
        choices.append(Separator("── Click Positions ──"))
        for name, desc in defs["positions"]:
            choices.append({
                "name": f"[position] {name} — {desc}",
                "value": ("position", name),
                "enabled": True,
            })

    return inquirer.checkbox(
        message="Select assets to capture (Space to toggle, Enter to confirm):",
        choices=choices,
        keybindings=VIM_NAV_KEYBINDINGS,
        validate=lambda res: len(res) > 0,
        invalid_message="You must select at least one asset.",
    ).execute()


def interactive_select_update_assets(game: str) -> list[str]:
    """
    Arrow-key checkbox to select which existing assets to re-capture.

    Reads the game's config to find all current elements and presents
    them as a selectable list.
    """
    config_path = PROJECT_ROOT / "config" / "games" / f"{game}.yaml"
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        print(f"Run a full capture first: python3 tools/capture.py --game {game}")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    defs = GAME_DEFS.get(game, {})

    # Build a lookup of all known asset descriptions for this game
    desc_map = {}
    for name, desc, *_ in defs.get("elements", []):
        desc_map[name] = desc
    for name, desc in defs.get("optional_elements", []):
        desc_map[name] = desc
    for name, desc in COMMON_OPTIONAL_ELEMENTS:
        desc_map[name] = desc

    # Existing elements from config
    elements = config.get("elements", {})
    if not elements:
        print(f"No elements found in config for '{game}'.")
        sys.exit(1)

    choices = []
    for elem_name in elements:
        desc = desc_map.get(elem_name, "")
        label = f"{elem_name} — {desc}" if desc else elem_name
        choices.append({"name": label, "value": elem_name})

    # Also offer assets that exist for this game but aren't captured yet
    all_possible = set(desc_map.keys())
    uncaptured = all_possible - set(elements.keys())
    if uncaptured:
        choices.append(Separator("── Not yet captured ──"))
        for name in sorted(uncaptured):
            desc = desc_map.get(name, "")
            label = f"{name} — {desc}" if desc else name
            choices.append({"name": label, "value": name})

    selected = inquirer.checkbox(
        message="Select assets to re-capture (Space to toggle, Enter to confirm):",
        choices=choices,
        keybindings=VIM_NAV_KEYBINDINGS,
        validate=lambda result: len(result) > 0,
        invalid_message="You must select at least one asset.",
    ).execute()

    return selected


def capture_selected_elements(
    game: str,
    selected_assets: list[tuple[str, str]],
) -> dict:
    """
    Capture only the user-selected assets for a game.

    Args:
        game: Game key from GAME_DEFS.
        selected_assets: List of (category, name) tuples from the interactive picker.

    Returns:
        Dict with 'elements', 'regions', 'positions', and 'asset_dir' keys.
    """
    asset_dir = PROJECT_ROOT / "assets" / game
    asset_dir.mkdir(parents=True, exist_ok=True)

    defs = GAME_DEFS[game]

    # Build lookup maps for descriptions
    elem_desc = {}
    for name, desc, *_ in defs["elements"]:
        elem_desc[name] = desc
    for name, desc in defs["optional_elements"]:
        elem_desc[name] = desc
    for name, desc in COMMON_OPTIONAL_ELEMENTS:
        elem_desc[name] = desc

    region_desc = {name: desc for name, desc in defs["regions"]}
    position_desc = {name: desc for name, desc in defs["positions"]}

    captured_elements = {}
    captured_regions = {}
    captured_positions = {}

    # Split selections by category
    sel_elements = [name for cat, name in selected_assets if cat == "element"]
    sel_regions = [name for cat, name in selected_assets if cat == "region"]
    sel_positions = [name for cat, name in selected_assets if cat == "position"]

    print(f"\n{'='*60}")
    print(f"  Capturing assets for: {game}")
    print(f"  Asset directory: {asset_dir}")
    print(f"{'='*60}")
    print()
    print("  Make sure the game is open and visible in Chrome.")
    print()

    # ── Capture template elements ──
    if sel_elements:
        print(f"--- Template Elements ({len(sel_elements)}) ---\n")
        for elem_name in sel_elements:
            desc = elem_desc.get(elem_name, "")
            print(f"  [{elem_name}] {desc}")
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

    # ── Capture OCR regions ──
    if sel_regions:
        print(f"\n--- OCR Regions ({len(sel_regions)}) ---\n")
        print("  For each region, select the area containing the number to read.\n")
        for region_name in sel_regions:
            desc = region_desc.get(region_name, "")
            print(f"  [{region_name}] {desc}")
            result = capture_screenshot_region()
            if result is None:
                print("    Failed — try again")
                result = capture_screenshot_region()
            if result is None:
                print("    Skipped.\n")
                continue

            img, region = result
            captured_regions[region_name] = region
            print(f"    Region: x={region['x']}, y={region['y']}, "
                  f"w={region['w']}, h={region['h']}")
            # Show OCR preview
            try:
                preview = _ocr_preview(img)
                print(f'    OCR preview: "{preview}"')
            except Exception:
                print("    OCR preview: <failed>")
            print()

    # ── Capture click positions ──
    if sel_positions:
        print(f"\n--- Click Positions ({len(sel_positions)}) ---\n")
        for pos_name in sel_positions:
            desc = position_desc.get(pos_name, "")
            pos = capture_position(f"[{pos_name}] {desc} — hover and press Enter")
            captured_positions[pos_name] = {"x": pos[0], "y": pos[1]}
            print()

    return {
        "elements": captured_elements,
        "regions": captured_regions,
        "positions": captured_positions,
        "asset_dir": f"assets/{game}/",
    }


def interactive_main() -> None:
    """Top-level interactive menu when no CLI flags are provided."""
    action = inquirer.select(
        message="What would you like to do?",
        choices=[
            {"name": "Capture new game assets", "value": "new"},
            {"name": "Redraw OCR regions (from saved screenshots)", "value": "redraw"},
            {"name": "Update existing assets", "value": "update"},
        ],
        keybindings=VIM_NAV_KEYBINDINGS,
    ).execute()

    if action == "new":
        interactive_new_game()
    elif action == "redraw":
        interactive_redraw_regions()
    elif action == "update":
        game = interactive_select_game()
        interactive_update_game(game)


def interactive_redraw_regions() -> None:
    """Interactive flow: select a game and redraw OCR regions from saved screenshots."""
    game = interactive_select_game()
    init_retina_scale()
    redraw_regions(game)


def interactive_new_game() -> None:
    """
    Full interactive flow: select game, pick assets, capture.

    Steps:
      1. Select game (arrow-key list)
      2. Select assets to capture (checkbox)
      3. Choose capture method (live vs snapshot, for live-dealer games)
      4. Capture and generate config
    """
    game = interactive_select_game()
    selected_assets = interactive_select_assets(game)

    # Offer snapshot mode for games with state groups (live-dealer games)
    if game in GAME_STATE_GROUPS:
        method = inquirer.select(
            message="Capture method:",
            choices=[
                {
                    "name": "Snapshot mode — screenshot each state first, then crop "
                            "(recommended for live games)",
                    "value": "snapshot",
                },
                {
                    "name": "Live mode — position cursor on screen for each element",
                    "value": "live",
                },
            ],
            keybindings=VIM_NAV_KEYBINDINGS,
        ).execute()
    else:
        method = "live"

    init_retina_scale()

    if method == "snapshot":
        captured = snapshot_capture_selected(game, selected_assets)
    else:
        captured = capture_selected_elements(game, selected_assets)

    config_path = generate_yaml_config(game, captured)

    print(f"\n{'='*60}")
    print(f"  Done! Next steps:")
    print(f"  1. Review config: {config_path}")
    print(f"  2. Test: python3 tools/capture.py --game {game} --test")
    print(f"  3. Run: python3 main.py --config {config_path} --duration 60")
    print(f"{'='*60}\n")


def interactive_update_game(game: str) -> None:
    """Interactive flow: select which assets to re-capture for an existing game."""
    selected = interactive_select_update_assets(game)

    init_retina_scale()

    for element_name in selected:
        update_single_asset(game, element_name)


def main():
    parser = argparse.ArgumentParser(
        description="Capture game assets and generate YAML configs"
    )
    parser.add_argument(
        "--game",
        choices=KNOWN_GAMES,
        help="Game to capture assets for",
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
        nargs="?",
        const="__interactive__",
        help="Re-capture asset(s). With a name: re-captures that asset. "
             "Without a name: interactive picker.",
    )
    parser.add_argument(
        "--help-game",
        metavar="GAME",
        help="Print a checklist of all assets needed for a game",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Use snapshot mode: take screenshots of each game state first, "
             "then crop assets from frozen images (recommended for live games)",
    )
    parser.add_argument(
        "--redraw-regions",
        action="store_true",
        help="Re-draw OCR regions on existing screenshots without taking new ones. "
             "Requires --game and a prior --snapshot run.",
    )

    args = parser.parse_args()

    # --help-game doesn't require --game
    if args.help_game:
        print_game_help(args.help_game)
        sys.exit(0)

    # No --game flag: enter fully interactive mode
    if not args.game:
        interactive_main()
        sys.exit(0)

    init_retina_scale()

    if args.redraw_regions:
        redraw_regions(args.game)
    elif args.update_asset:
        if args.update_asset == "__interactive__":
            interactive_update_game(args.game)
        else:
            update_single_asset(args.game, args.update_asset)
    elif args.reset:
        reset_game(args.game)
        captured = capture_elements(args.game)
        config_path = generate_yaml_config(args.game, captured)
        print(f"\n{'='*60}")
        print(f"  Re-captured! Config: {config_path}")
        print(f"  Run: python3 main.py --config {config_path} --duration 60")
        print(f"{'='*60}\n")
    elif args.test:
        test_assets(args.game)
    else:
        if args.snapshot:
            captured = snapshot_capture(args.game)
        else:
            captured = capture_elements(args.game)
        config_path = generate_yaml_config(args.game, captured)

        print(f"\n{'='*60}")
        print(f"  Done! Next steps:")
        print(f"  1. Review config: {config_path}")
        print(f"  2. Test: python3 tools/capture.py --game {args.game} --test")
        print(f"  3. Run: python3 main.py --config {config_path} --duration 60")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
