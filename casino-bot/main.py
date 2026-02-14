#!/usr/bin/env python3
"""
Casino Leaderboard Bot — Main Entry Point

Usage:
  # Interactive mode (arrow-key menu to select game and duration)
  python3 main.py

  # CLI mode (specify config and duration directly)
  python3 main.py --config config/games/crazy_time.yaml
  python3 main.py --config config/games/crazy_time.yaml --duration 90
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on the Python path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.screen import init_retina_scale

# Game runner registry — maps game key to (display name, runner class path, config filename)
GAME_REGISTRY = {
    "crazy_time": {
        "name": "Crazy Time",
        "runner": "src.games.crazy_time.CrazyTimeGame",
        "config": "crazy_time.yaml",
    },
    "diamond_wild": {
        "name": "Diamond Wild",
        "runner": "src.games.diamond_wild.DiamondWildGame",
        "config": "diamond_wild.yaml",
    },
    "infinite_blackjack": {
        "name": "Infinite Blackjack",
        "runner": "src.games.infinite_blackjack.InfiniteBlackjackGame",
        "config": "infinite_blackjack.yaml",
    },
    "slot": {
        "name": "Slots",
        "runner": "src.games.slots.SlotsGame",
        "config": "slot_template.yaml",
    },
}

# Flat lookup for legacy --config detection (config stem → game key)
_CONFIG_STEM_TO_GAME = {}
for _key, _info in GAME_REGISTRY.items():
    _CONFIG_STEM_TO_GAME[Path(_info["config"]).stem] = _key
    _CONFIG_STEM_TO_GAME[_key] = _key  # also allow game key as stem


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the bot."""
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(level)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    # Quiet down noisy libraries
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("pytesseract").setLevel(logging.WARNING)


def detect_game(config_path: str) -> str:
    """Detect the game from the config filename."""
    stem = Path(config_path).stem
    game = _CONFIG_STEM_TO_GAME.get(stem)
    if game is None:
        print(f"Error: Unknown game '{stem}'")
        print(f"Supported games: {', '.join(GAME_REGISTRY.keys())}")
        sys.exit(1)
    return game


def get_runner_class(game: str):
    """Import and return the game runner class for a given game."""
    info = GAME_REGISTRY.get(game)
    if not info:
        print(f"Error: Unknown game '{game}'")
        print(f"Supported games: {', '.join(GAME_REGISTRY.keys())}")
        sys.exit(1)

    class_path = info["runner"]
    module_path, class_name = class_path.rsplit(".", 1)
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)


# ── Interactive mode ──────────────────────────────────────────────────────

# Shared keybindings: arrow keys (default) + vim j/k
VIM_NAV_KEYBINDINGS = {
    "down": [{"key": "down"}, {"key": "j"}],
    "up": [{"key": "up"}, {"key": "k"}],
}


def _available_games() -> list[dict]:
    """
    Return the list of games that have a config file ready.
    Each entry is {"key": ..., "name": ..., "config_path": Path(...)}.
    """
    config_dir = PROJECT_ROOT / "config" / "games"
    available = []
    for key, info in GAME_REGISTRY.items():
        cfg = config_dir / info["config"]
        if cfg.exists():
            available.append({
                "key": key,
                "name": info["name"],
                "config_path": cfg,
            })
    return available


def interactive_select_game(games: list[dict]) -> dict:
    """Arrow-key menu to select which game to run."""
    from InquirerPy import inquirer

    choices = [
        {"name": g["name"], "value": g}
        for g in games
    ]
    return inquirer.select(
        message="Select a game to run:",
        choices=choices,
        keybindings=VIM_NAV_KEYBINDINGS,
    ).execute()


def interactive_get_duration() -> float:
    """Prompt the user to type a session duration in minutes."""
    from InquirerPy import inquirer

    duration_str = inquirer.text(
        message="Session duration in minutes (leave blank for no limit):",
        default="",
        validate=lambda val: val == "" or val.replace(".", "", 1).isdigit(),
        invalid_message="Please enter a positive number (or leave blank).",
    ).execute()

    if duration_str.strip() == "":
        return None
    return float(duration_str)


def interactive_mode(verbose: bool = False):
    """Fully interactive flow: select game → enter duration → run."""
    games = _available_games()

    if not games:
        print("No game configs found in config/games/.")
        print("Run the capture tool first: python3 tools/capture.py")
        sys.exit(1)

    # Step 1: Select game
    selected = interactive_select_game(games)

    # Step 2: Enter duration
    duration = interactive_get_duration()

    # Setup and run
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    logger.info("Casino Leaderboard Bot starting...")
    logger.info(f"Game: {selected['name']}")
    logger.info(f"Config: {selected['config_path']}")
    if duration:
        logger.info(f"Duration: {duration} minutes")
    else:
        logger.info("Duration: no limit (Ctrl+C to stop)")

    init_retina_scale()

    RunnerClass = get_runner_class(selected["key"])
    runner = RunnerClass(selected["config_path"])
    runner.run(duration_minutes=duration)


# ── CLI mode (legacy --config flag) ──────────────────────────────────────

def cli_mode(args):
    """Run with explicit --config and --duration flags."""
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("Casino Leaderboard Bot starting...")
    logger.info(f"Config: {config_path}")

    init_retina_scale()

    game = detect_game(str(config_path))
    logger.info(f"Game: {game}")

    RunnerClass = get_runner_class(game)
    runner = RunnerClass(config_path)
    runner.run(duration_minutes=args.duration)


# ── Entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Casino Leaderboard Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python3 main.py

  # CLI mode
  python3 main.py --config config/games/crazy_time.yaml
  python3 main.py --config config/games/crazy_time.yaml --duration 90
  python3 main.py --config config/games/slot_template.yaml --duration 30 --verbose
        """,
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to game YAML config file (omit for interactive mode)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Session duration in minutes (overrides config value)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.config:
        cli_mode(args)
    else:
        interactive_mode(verbose=args.verbose)


if __name__ == "__main__":
    main()
