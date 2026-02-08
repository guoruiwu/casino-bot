"""
Crazy Time Live game runner.

State machine:
  IDLE -> BETTING -> WAITING_FOR_SPIN -> RESULT -> (BONUS_ROUND?) -> IDLE

Bonus rounds:
  - Cash Hunt: interactive (click a spot on the grid)
  - Coin Flip: passive (wait for result)
  - Pachinko: passive (wait for result)
  - Crazy Time: passive (may need to click flapper choice)
"""

from __future__ import annotations

import logging
import random
import time
from enum import Enum
from pathlib import Path

from src.actions import (
    click_element,
    click_position,
    click_region_random,
    move_mouse_away,
    random_delay,
)
from src.games.base_game import BaseGame
from src.screen import (
    find_element,
    read_number,
    take_screenshot,
    wait_for_element,
)

logger = logging.getLogger(__name__)


class CrazyTimeState(str, Enum):
    """Possible states for the Crazy Time state machine."""

    IDLE = "idle"                         # Waiting (wheel spinning, bonus, etc.)
    BETTING = "betting"                   # Betting phase is open
    BONUS_CASH_HUNT = "bonus_cash_hunt"   # Cash Hunt bonus (needs interaction)


class CrazyTimeGame(BaseGame):
    """Crazy Time Live game runner for DraftKings."""

    def __init__(self, config_path: str | Path):
        super().__init__(config_path)

        # Crazy Time specific config
        self.bets_config: list[dict] = self.config.get("bets", [])
        self.poll_interval = self.settings.get("poll_interval", 2.0)

        # State tracking
        self._bets_placed_this_round = False
        self._last_state = CrazyTimeState.IDLE

        logger.info(f"Configured bets: {len(self.bets_config)} segments")
        for bet in self.bets_config:
            logger.info(f"  {bet['segment']} at ({bet.get('click_x')}, {bet.get('click_y')})")

    def on_start(self) -> None:
        """Read initial balance."""
        balance = self._read_balance()
        if balance is not None:
            self.starting_balance = balance
            self.current_balance = balance
            logger.info(f"Starting balance: ${balance:.2f}")

    # ── State Detection ──────────────────────────────────────────────────

    def detect_state(self) -> str:
        """
        Determine current Crazy Time game state from the screen.

        Only needs one signal: is betting_open visible?
          - Yes → BETTING (place bets)
          - No  → IDLE (wait for next round)

        Cash Hunt bonus is detected separately if configured.
        """
        screenshot = take_screenshot()

        # Check for Cash Hunt bonus (needs interaction) if configured
        bonus_cashhunt = self.get_element("bonus_cashhunt")
        if bonus_cashhunt and find_element(
            bonus_cashhunt, self.confidence, screenshot=screenshot
        ):
            return CrazyTimeState.BONUS_CASH_HUNT

        # The only required signal: is betting open?
        betting_open = self.get_element("betting_open")
        if betting_open and find_element(
            betting_open, self.confidence, screenshot=screenshot
        ):
            return CrazyTimeState.BETTING

        return CrazyTimeState.IDLE

    # ── Step Execution ───────────────────────────────────────────────────

    def step(self, state: str) -> None:
        """Execute one step based on current state."""
        # Log state transitions
        if state != self._last_state:
            logger.info(f"State: {self._last_state} -> {state}")

            # If we just transitioned from BETTING to IDLE, a round ended
            if self._last_state == CrazyTimeState.BETTING and state == CrazyTimeState.IDLE:
                self._on_round_end()

            self._last_state = state

        handlers = {
            CrazyTimeState.IDLE: self._step_idle,
            CrazyTimeState.BETTING: self._step_betting,
            CrazyTimeState.BONUS_CASH_HUNT: self._step_bonus_cash_hunt,
        }

        handler = handlers.get(state, self._step_idle)
        handler()

    # ── State Handlers ───────────────────────────────────────────────────

    def _step_idle(self) -> None:
        """Waiting — wheel spinning, bonus playing out, or between rounds."""
        self._bets_placed_this_round = False
        time.sleep(self.poll_interval)

    def _on_round_end(self) -> None:
        """Called when betting closes (round started). Read balance and log."""
        balance = self._read_balance()
        self.log_round(balance=balance, notes="round")

    def _step_betting(self) -> None:
        """Place bets on configured segments using click coordinates."""
        if self._bets_placed_this_round:
            # Already placed bets this round — just wait
            time.sleep(self.poll_interval)
            return

        logger.info("Betting phase — placing bets...")

        # Shuffle bet order to vary behavior each round
        bets_shuffled = list(self.bets_config)
        random.shuffle(bets_shuffled)

        for bet in bets_shuffled:
            segment = bet["segment"]

            # Prefer coordinate-based clicking (simpler, no image matching needed)
            if "click_x" in bet and "click_y" in bet:
                click_position(
                    bet["click_x"], bet["click_y"],
                    jitter=True, delay_range=(0.2, 0.5),
                )
                logger.info(f"Bet placed: {segment} (${bet['amount']:.2f})")
            else:
                # Fallback: image matching for bet segments
                bet_segments = self.get_element_dict("bet_segments")
                segment_img = bet_segments.get(segment)
                if segment_img is None:
                    logger.warning(f"No asset or coordinates for segment: {segment}")
                    continue
                if click_element(segment_img, self.confidence, delay_range=(0.2, 0.5)):
                    logger.info(f"Bet placed: {segment} (${bet['amount']:.2f})")
                else:
                    logger.warning(f"Could not find segment: {segment}")

        # Confirm bet if there's a confirm button
        confirm = self.get_element("confirm_bet")
        if confirm:
            click_element(confirm, self.confidence, delay_range=(0.3, 0.5))

        self._bets_placed_this_round = True
        move_mouse_away()
        logger.info("All bets placed — waiting for spin")

    # ── Bonus Round Handlers ─────────────────────────────────────────────

    def _step_bonus_cash_hunt(self) -> None:
        """
        Cash Hunt bonus: click a random spot in the prize grid.

        Cash Hunt shows a grid of random multipliers hidden behind icons.
        The player picks one spot.
        """
        logger.info("BONUS: Cash Hunt — picking a spot!")
        random_delay(1.0, 2.0)

        cash_hunt_region = self.get_region("cash_hunt_grid")
        if cash_hunt_region:
            click_region_random(cash_hunt_region)
            logger.info("Cash Hunt: spot selected")
        else:
            # Fallback: click center of screen
            logger.warning("Cash Hunt grid region not configured — clicking center")
            import pyautogui
            screen_w, screen_h = pyautogui.size()
            click_position(screen_w // 2, screen_h // 2, jitter=True)

        # Wait for Cash Hunt result — just wait for betting_open to reappear
        betting_open = self.get_element("betting_open")
        if betting_open:
            wait_for_element(betting_open, self.confidence, timeout=60, poll_interval=3)
        else:
            time.sleep(15)

        balance = self._read_balance()
        self.log_round(balance=balance, notes="bonus_cash_hunt")
        logger.info("Cash Hunt bonus complete")

    # ── Utilities ────────────────────────────────────────────────────────

    def _read_balance(self) -> float | None:
        """Read current balance via OCR."""
        balance_region = self.get_region("balance")
        if not balance_region:
            return None

        balance = read_number(balance_region)
        if balance is not None:
            logger.debug(f"Balance: ${balance:.2f}")
        return balance
