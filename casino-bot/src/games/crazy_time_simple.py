"""
Crazy Time Simple — just bet on '1' every round.

Dead simple state machine:
  WAITING  →  (betting_open detected)  →  BETTING  →  (click bet_1)  →  COOLDOWN  →  WAITING

Only needs two template images:
  - betting_open.png  (to know when we can bet)
  - bet_1.png         (where to click)
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from pathlib import Path

from src.actions import click_element, move_mouse_away, random_delay
from src.games.base_game import BaseGame
from src.screen import find_element, take_screenshot

logger = logging.getLogger(__name__)


class State(str, Enum):
    WAITING = "waiting"       # Waiting for betting to open
    BETTING = "betting"       # Betting is open — place bet
    COOLDOWN = "cooldown"     # Bet placed — wait for round to finish


class CrazyTimeSimpleGame(BaseGame):
    """Minimal Crazy Time bot: detect betting phase, click '1', repeat."""

    def __init__(self, config_path: str | Path):
        super().__init__(config_path)

        self.poll_interval: float = self.settings.get("poll_interval", 1.5)
        self.cooldown_time: float = self.settings.get("cooldown", 15.0)

        self._state = State.WAITING
        self._cooldown_start: float = 0.0

    def on_start(self) -> None:
        logger.info("Simple mode: betting on '1' every round")
        logger.info(f"Poll interval: {self.poll_interval}s | Cooldown: {self.cooldown_time}s")

    # ── State detection ───────────────────────────────────────────

    def detect_state(self) -> str:
        # During cooldown, just wait — don't even check the screen
        if self._state == State.COOLDOWN:
            elapsed = time.time() - self._cooldown_start
            if elapsed < self.cooldown_time:
                return State.COOLDOWN
            else:
                self._state = State.WAITING

        # Check if betting is open
        betting_open = self.get_element("betting_open")
        if betting_open and find_element(betting_open, self.confidence):
            return State.BETTING

        return State.WAITING

    # ── Step execution ────────────────────────────────────────────

    def step(self, state: str) -> None:
        if state == State.BETTING:
            self._place_bet()
        elif state == State.COOLDOWN:
            time.sleep(1.0)
        else:
            # WAITING — poll
            time.sleep(self.poll_interval)

    def _place_bet(self) -> None:
        """Click the '1' bet area."""
        bet_segments = self.get_element_dict("bet_segments")
        bet_1 = bet_segments.get("1")

        if bet_1 is None:
            logger.error("No bet_1 asset configured — can't place bet!")
            time.sleep(self.poll_interval)
            return

        if click_element(bet_1, self.confidence, delay_range=(0.2, 0.5)):
            self.rounds_played += 1
            logger.info(f"[Round {self.rounds_played}] Bet placed on '1'")
        else:
            logger.warning("Could not find '1' bet area on screen")

        move_mouse_away()

        # Enter cooldown to avoid re-betting the same round
        self._state = State.COOLDOWN
        self._cooldown_start = time.time()
