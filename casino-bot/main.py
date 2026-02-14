#!/usr/bin/env python3
"""
Casino Leaderboard Bot — Main Entry Point

Usage:
  python3 main.py --config config/games/crazy_time_dk.yaml
  python3 main.py --config config/games/crazy_time_dk.yaml --duration 90
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on the Python path
sys.path.insert(0, str(Path(__file__).parent))

from src.screen import init_retina_scale

# Game runner registry — maps game to runner class
GAME_RUNNERS = {
    "slot": "src.games.slots.SlotsGame",
    "crazy_time": "src.games.crazy_time.CrazyTimeGame",
    "diamond_wild": "src.games.diamond_wild.DiamondWildGame",
    "infinite_blackjack": "src.games.infinite_blackjack.InfiniteBlackjackGame",
}


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
    """Detect the game from the config filename using prefix matching."""
    stem = Path(config_path).stem
    known_games = sorted(GAME_RUNNERS.keys(), key=len, reverse=True)
    for game in known_games:
        if stem == game or stem.startswith(game + "_"):
            return game

    print(f"Error: Could not detect game from config filename '{stem}'")
    print(f"Supported games: {', '.join(GAME_RUNNERS.keys())}")
    sys.exit(1)


def get_runner_class(game: str):
    """Import and return the game runner class for a given game."""
    class_path = GAME_RUNNERS.get(game)
    if not class_path:
        print(f"Error: Unknown game '{game}'")
        print(f"Supported games: {', '.join(GAME_RUNNERS.keys())}")
        sys.exit(1)

    # Dynamic import
    module_path, class_name = class_path.rsplit(".", 1)
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)


def main():
    parser = argparse.ArgumentParser(
        description="Casino Leaderboard Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py --config config/games/crazy_time_dk.yaml
  python3 main.py --config config/games/crazy_time_dk.yaml --duration 90
  python3 main.py --config config/games/my_slot.yaml --duration 30 --verbose
        """,
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to game YAML config file",
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

    # Validate config file exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    # Setup
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("Casino Leaderboard Bot starting...")
    logger.info(f"Config: {config_path}")

    # Initialize Retina scale detection
    init_retina_scale()

    # Detect game and get runner
    game = detect_game(str(config_path))
    logger.info(f"Game: {game}")

    RunnerClass = get_runner_class(game)
    runner = RunnerClass(config_path)

    # Run the game
    runner.run(duration_minutes=args.duration)


if __name__ == "__main__":
    main()
