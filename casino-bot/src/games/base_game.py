"""
Abstract base class for all game runners.

Provides config loading, session timer, logging, error handling, and the main game loop
structure. Each game type (slots, crazy_time, etc.) subclasses this and implements
detect_state() and step().
"""

from __future__ import annotations

import csv
import datetime
import logging
import os
import signal
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


class BaseGame(ABC):
    """Abstract base class for game runners."""

    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self.config: dict = {}
        self.asset_dir: Path = Path(".")
        self.elements: dict[str, Path] = {}
        self.regions: dict[str, dict] = {}
        self.settings: dict = {}

        # Session state
        self.session_start: float = 0.0
        self.session_duration: float = 60.0  # minutes
        self.rounds_played: int = 0
        self.starting_balance: Optional[float] = None
        self.current_balance: Optional[float] = None
        self.running: bool = False

        # Logging
        self.log_file: Optional[str] = None

        # Load config
        self._load_config()

    def _load_config(self) -> None:
        """Load and parse the YAML game config file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            self.config = yaml.safe_load(f)

        game_cfg = self.config.get("game", {})
        self.game_name = game_cfg.get("name", "Unknown Game")
        self.game_type = game_cfg.get("type", "unknown")
        self.platform = game_cfg.get("platform", "unknown")

        # Resolve asset directory relative to project root
        asset_dir_str = game_cfg.get("asset_dir", "assets/")
        self.asset_dir = self._resolve_path(asset_dir_str)

        # Load elements — resolve each to full path
        raw_elements = self.config.get("elements", {})
        self.elements = {}
        for key, value in raw_elements.items():
            if isinstance(value, str):
                self.elements[key] = self.asset_dir / value
            elif isinstance(value, dict):
                # Nested elements (e.g. bet_segments)
                self.elements[key] = {
                    k: self.asset_dir / v for k, v in value.items()
                }

        # Load regions
        self.regions = self.config.get("regions", {})

        # Load settings
        self.settings = self.config.get("settings", {})
        self.session_duration = self.settings.get("session_duration", 60.0)
        self.confidence = self.settings.get("confidence", 0.85)
        self.action_delay = tuple(self.settings.get("action_delay", [0.3, 1.0]))

        logger.info(f"Loaded config: {self.game_name} ({self.game_type})")
        logger.info(f"Asset dir: {self.asset_dir}")
        logger.info(f"Session duration: {self.session_duration} minutes")

    def _resolve_path(self, relative_path: str) -> Path:
        """Resolve a path relative to the project root (parent of config/)."""
        project_root = self.config_path.parent.parent.parent
        resolved = project_root / relative_path
        return resolved

    def get_element(self, key: str) -> Optional[Path]:
        """Get the full path to an element template image."""
        el = self.elements.get(key)
        if el is None:
            logger.warning(f"Element not configured: {key}")
        return el

    def get_element_dict(self, key: str) -> dict[str, Path]:
        """Get a dict of element paths (for nested elements like bet_segments)."""
        el = self.elements.get(key, {})
        if isinstance(el, dict):
            return el
        return {}

    def get_region(self, key: str) -> Optional[dict]:
        """Get a screen region definition."""
        region = self.regions.get(key)
        if region is None:
            logger.warning(f"Region not configured: {key}")
        return region

    @property
    def time_remaining(self) -> float:
        """Seconds remaining in the session."""
        elapsed = time.time() - self.session_start
        remaining = (self.session_duration * 60) - elapsed
        return max(remaining, 0)

    @property
    def session_expired(self) -> bool:
        """Whether the session timer has run out."""
        return self.time_remaining <= 0

    def _setup_signal_handlers(self) -> None:
        """Set up Ctrl+C handler for graceful shutdown."""
        def handle_sigint(sig, frame):
            logger.info("\nCtrl+C detected — stopping after current action...")
            self.running = False

        signal.signal(signal.SIGINT, handle_sigint)

    def _init_log_file(self) -> None:
        """Initialize the CSV log file for round results."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        game_slug = self.game_name.replace(" ", "_").replace("-", "_").lower()
        log_dir = self._resolve_path("logs")
        log_dir.mkdir(exist_ok=True)
        self.log_file = str(log_dir / f"{game_slug}_{timestamp}.csv")

        with open(self.log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "round", "balance", "notes"])

        logger.info(f"Logging rounds to: {self.log_file}")

    def log_round(self, balance: Optional[float] = None, notes: str = "") -> None:
        """Log a round result to the CSV file and console."""
        self.rounds_played += 1
        if balance is not None:
            self.current_balance = balance

        if self.log_file:
            with open(self.log_file, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.datetime.now().isoformat(),
                    self.rounds_played,
                    balance,
                    notes,
                ])

        # Periodic console summary
        if self.rounds_played % 10 == 0:
            self._print_status()

    def _print_status(self) -> None:
        """Print a status summary to the console."""
        elapsed = time.time() - self.session_start
        elapsed_min = elapsed / 60

        status = (
            f"[Round {self.rounds_played}] "
            f"Time: {elapsed_min:.1f}/{self.session_duration:.0f} min"
        )

        if self.starting_balance is not None and self.current_balance is not None:
            pnl = self.current_balance - self.starting_balance
            sign = "+" if pnl >= 0 else ""
            status += f" | Balance: ${self.current_balance:.2f} ({sign}${pnl:.2f})"

        logger.info(status)

    def on_error(self, error: Exception, context: str = "") -> None:
        """
        Handle unexpected errors during gameplay.

        Takes a screenshot for debugging, logs the error, and pauses briefly
        before retrying.
        """
        logger.error(f"Error during {context}: {error}")

        # Save an error screenshot for debugging
        try:
            from src.screen import take_screenshot
            import cv2

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            error_dir = self._resolve_path("errors")
            error_dir.mkdir(exist_ok=True)
            screenshot = take_screenshot()
            error_path = str(error_dir / f"error_{timestamp}.png")
            cv2.imwrite(error_path, screenshot)
            logger.info(f"Error screenshot saved: {error_path}")
        except Exception as e:
            logger.error(f"Failed to save error screenshot: {e}")

        # Pause before retrying
        time.sleep(5)

    @abstractmethod
    def detect_state(self) -> str:
        """
        Determine the current game state by examining the screen.

        Returns:
            A string representing the current state (e.g. "idle", "spinning",
            "bonus_pick", etc.). State names are game-type specific.
        """
        ...

    @abstractmethod
    def step(self, state: str) -> None:
        """
        Execute one step of the game loop based on current state.

        Args:
            state: The current game state as returned by detect_state().
        """
        ...

    def on_start(self) -> None:
        """Called once when the game session starts. Override for setup logic."""
        pass

    def on_stop(self) -> None:
        """Called once when the game session ends. Override for cleanup logic."""
        pass

    def run(self, duration_minutes: Optional[float] = None) -> None:
        """
        Main game loop. Runs until session timer expires or Ctrl+C.

        Args:
            duration_minutes: Override session duration from config.
        """
        if duration_minutes is not None:
            self.session_duration = duration_minutes

        self.session_start = time.time()
        self.running = True

        self._setup_signal_handlers()
        self._init_log_file()

        logger.info(f"Starting {self.game_name}")
        logger.info(f"Session duration: {self.session_duration} minutes")
        logger.info("Press Ctrl+C to stop gracefully.")
        print()

        self.on_start()

        try:
            while self.running and not self.session_expired:
                try:
                    state = self.detect_state()
                    self.step(state)
                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt — stopping...")
                    break
                except Exception as e:
                    self.on_error(e, context="game loop")
                    if not self.running:
                        break
        finally:
            self.on_stop()
            self._print_final_summary()

    def _print_final_summary(self) -> None:
        """Print final session summary."""
        elapsed = time.time() - self.session_start
        elapsed_min = elapsed / 60

        print()
        logger.info("=" * 50)
        logger.info(f"Session Complete: {self.game_name}")
        logger.info(f"Duration: {elapsed_min:.1f} minutes")
        logger.info(f"Rounds played: {self.rounds_played}")

        if self.starting_balance is not None and self.current_balance is not None:
            pnl = self.current_balance - self.starting_balance
            sign = "+" if pnl >= 0 else ""
            logger.info(f"Starting balance: ${self.starting_balance:.2f}")
            logger.info(f"Ending balance: ${self.current_balance:.2f}")
            logger.info(f"P&L: {sign}${pnl:.2f}")

        if self.log_file:
            logger.info(f"Log file: {self.log_file}")

        logger.info("=" * 50)
