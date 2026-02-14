"""
Infinite Blackjack (Live Dealer) game runner.

State machine:
  WAITING -> BETTING -> WAITING -> DECISION -> (DECISION on HIT) -> WAITING -> ...

Rules (FanDuel Infinite Blackjack):
  - Dealer must hit soft 17
  - Blackjack pays 3 to 2
  - Insurance pays 2 to 1
  - No splitting (per user preference)
  - Always bet $1
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from pathlib import Path
from typing import Optional

from src.actions import (
    click_element,
    click_position,
    move_mouse_away,
    random_delay,
)
from src.games.base_game import BaseGame
from src.screen import (
    find_element,
    read_number,
    take_screenshot,
)

logger = logging.getLogger(__name__)


# ── Basic Strategy (Hard Totals, Dealer Hits Soft 17) ────────────────────
#
# Action codes: H = Hit, S = Stand, D = Double (hit if not allowed)
#
# Rows: player hard total (4-20)
# Columns: dealer upcard (2-11, where 11 = Ace)

BASIC_STRATEGY: dict[int, dict[int, str]] = {
    # player_total: {dealer_total: action}
    4:  {2: "H", 3: "H", 4: "H", 5: "H", 6: "H", 7: "H", 8: "H", 9: "H", 10: "H", 11: "H"},
    5:  {2: "H", 3: "H", 4: "H", 5: "H", 6: "H", 7: "H", 8: "H", 9: "H", 10: "H", 11: "H"},
    6:  {2: "H", 3: "H", 4: "H", 5: "H", 6: "H", 7: "H", 8: "H", 9: "H", 10: "H", 11: "H"},
    7:  {2: "H", 3: "H", 4: "H", 5: "H", 6: "H", 7: "H", 8: "H", 9: "H", 10: "H", 11: "H"},
    8:  {2: "H", 3: "H", 4: "H", 5: "H", 6: "H", 7: "H", 8: "H", 9: "H", 10: "H", 11: "H"},
    9:  {2: "H", 3: "H", 4: "D", 5: "D", 6: "D", 7: "H", 8: "H", 9: "H", 10: "H", 11: "H"},
    10: {2: "D", 3: "D", 4: "D", 5: "D", 6: "D", 7: "D", 8: "D", 9: "D", 10: "H", 11: "H"},
    11: {2: "D", 3: "D", 4: "D", 5: "D", 6: "D", 7: "D", 8: "D", 9: "D", 10: "D", 11: "D"},
    12: {2: "H", 3: "H", 4: "S", 5: "S", 6: "S", 7: "H", 8: "H", 9: "H", 10: "H", 11: "H"},
    13: {2: "S", 3: "S", 4: "S", 5: "S", 6: "S", 7: "H", 8: "H", 9: "H", 10: "H", 11: "H"},
    14: {2: "S", 3: "S", 4: "S", 5: "S", 6: "S", 7: "H", 8: "H", 9: "H", 10: "H", 11: "H"},
    15: {2: "S", 3: "S", 4: "S", 5: "S", 6: "S", 7: "H", 8: "H", 9: "H", 10: "H", 11: "H"},
    16: {2: "S", 3: "S", 4: "S", 5: "S", 6: "S", 7: "H", 8: "H", 9: "H", 10: "H", 11: "H"},
    17: {2: "S", 3: "S", 4: "S", 5: "S", 6: "S", 7: "S", 8: "S", 9: "S", 10: "S", 11: "S"},
    18: {2: "S", 3: "S", 4: "S", 5: "S", 6: "S", 7: "S", 8: "S", 9: "S", 10: "S", 11: "S"},
    19: {2: "S", 3: "S", 4: "S", 5: "S", 6: "S", 7: "S", 8: "S", 9: "S", 10: "S", 11: "S"},
    20: {2: "S", 3: "S", 4: "S", 5: "S", 6: "S", 7: "S", 8: "S", 9: "S", 10: "S", 11: "S"},
}


def get_action(player_total: int, dealer_upcard: int) -> str:
    """
    Look up the basic strategy action for a given hand.

    Args:
        player_total: Player's hand total (4-21).
        dealer_total: Dealer's visible card value (2-11, where 11 = Ace).

    Returns:
        "hit", "stand", or "double".
    """
    # Clamp inputs to valid ranges
    dealer_upcard = max(2, min(11, dealer_upcard))

    if player_total <= 4:
        return "hit"
    if player_total >= 17:
        return "stand"

    row = BASIC_STRATEGY.get(player_total)
    if row is None:
        # Fallback: hit if under 17
        return "hit" if player_total < 17 else "stand"

    code = row.get(dealer_upcard, "H")

    if code == "H":
        return "hit"
    elif code == "S":
        return "stand"
    elif code == "D":
        return "double"
    else:
        return "hit"


class InfiniteBlackjackState(str, Enum):
    """Possible states for the Infinite Blackjack state machine."""

    WAITING = "waiting"     # Dealer playing, results showing, between rounds
    BETTING = "betting"     # "PLACE YOUR BETS" — betting phase is open
    DECISION = "decision"   # "MAKE YOUR DECISION" — player must act


class InfiniteBlackjackGame(BaseGame):
    """Infinite Blackjack (Live Dealer) game runner."""

    def __init__(self, config_path: str | Path):
        super().__init__(config_path)

        # Blackjack-specific config
        self.bet_spot: dict = self.config.get("bet_spot", {})
        self.poll_interval: float = self.settings.get("poll_interval", 1.0)

        # State tracking
        self._bet_placed_this_round: bool = False
        self._decision_made_this_step: bool = False
        self._last_state: str = InfiniteBlackjackState.WAITING

        logger.info(f"Bet spot: ({self.bet_spot.get('x')}, {self.bet_spot.get('y')})")

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
        Determine current game state from the screen.

        Priority:
          1. HIT button visible → DECISION (player must act)
          2. betting_open visible → BETTING (place bets)
          3. Otherwise → WAITING
        """
        screenshot = take_screenshot()

        # Check for decision phase first (HIT button is the most reliable signal)
        hit_button = self.get_element("hit_button")
        if hit_button and find_element(
            hit_button, self.confidence, screenshot=screenshot
        ):
            return InfiniteBlackjackState.DECISION

        # Check for betting phase
        betting_open = self.get_element("betting_open")
        if betting_open and find_element(
            betting_open, self.confidence, screenshot=screenshot
        ):
            return InfiniteBlackjackState.BETTING

        return InfiniteBlackjackState.WAITING

    # ── Step Execution ───────────────────────────────────────────────────

    def step(self, state: str) -> None:
        """Execute one step based on current state."""
        # Log state transitions
        if state != self._last_state:
            logger.info(f"State: {self._last_state} -> {state}")

            # Transitioned out of BETTING → round started, log it
            if (
                self._last_state == InfiniteBlackjackState.BETTING
                and state == InfiniteBlackjackState.WAITING
            ):
                self._on_round_end()

            # Transitioned to BETTING → new round, reset flags
            if state == InfiniteBlackjackState.BETTING:
                self._bet_placed_this_round = False

            self._last_state = state

        handlers = {
            InfiniteBlackjackState.WAITING: self._step_waiting,
            InfiniteBlackjackState.BETTING: self._step_betting,
            InfiniteBlackjackState.DECISION: self._step_decision,
        }

        handler = handlers.get(state, self._step_waiting)
        handler()

    # ── State Handlers ───────────────────────────────────────────────────

    def _step_waiting(self) -> None:
        """Waiting — dealer playing, results showing, or between rounds."""
        time.sleep(self.poll_interval)

    def _on_round_end(self) -> None:
        """Called when a round ends. Read balance and log."""
        balance = self._read_balance()
        self.log_round(balance=balance, notes="round")

    def _step_betting(self) -> None:
        """Place a $1 bet during the betting phase."""
        if self._bet_placed_this_round:
            time.sleep(self.poll_interval)
            return

        logger.info("Betting phase — placing $1 bet...")

        # Try REPEAT button first (available after the first round)
        repeat_button = self.get_element("repeat_button")
        if repeat_button and click_element(
            repeat_button, self.confidence, delay_range=(0.3, 0.6)
        ):
            logger.info("Bet placed via REPEAT")
            self._bet_placed_this_round = True
            move_mouse_away()
            return

        # Fallback: click $1 chip, then click the bet spot
        chip_1 = self.get_element("chip_1")
        if chip_1 and click_element(
            chip_1, self.confidence, delay_range=(0.2, 0.4)
        ):
            # Now click the bet spot on the table
            if self.bet_spot:
                click_position(
                    self.bet_spot["x"],
                    self.bet_spot["y"],
                    jitter=True,
                    delay_range=(0.2, 0.4),
                )
                logger.info("Bet placed: $1 chip → bet spot")
                self._bet_placed_this_round = True
            else:
                logger.warning("bet_spot not configured — cannot place bet")
        else:
            logger.warning("Could not find $1 chip on screen")

        move_mouse_away()

    def _step_decision(self) -> None:
        """
        Read player total and dealer upcard, then act according to basic strategy.

        After clicking, the game loop will call detect_state() again.
        If we hit and need another decision, DECISION state will be detected again.
        """
        # Read player total
        player_total = self._read_player_total()
        if player_total is None:
            logger.warning("Could not read player total — defaulting to stand")
            self._click_stand()
            return

        # Read dealer total
        dealer_total = self._read_dealer_total()
        if dealer_total is None:
            logger.warning("Could not read dealer total — using conservative play")
            # Conservative fallback: stand on 12+, hit on 11 or less
            if player_total >= 12:
                self._click_stand()
            else:
                self._click_hit()
            return

        # Look up basic strategy
        action = get_action(player_total, dealer_total)
        logger.info(
            f"Player: {player_total}, Dealer: {dealer_total} → {action.upper()}"
        )

        if action == "double":
            self._click_double(fallback_hit=True)
        elif action == "stand":
            self._click_stand()
        else:
            self._click_hit()

    # ── Action Clicks ────────────────────────────────────────────────────

    def _click_hit(self) -> None:
        """Click the HIT button."""
        hit_button = self.get_element("hit_button")
        if hit_button:
            if click_element(hit_button, self.confidence, delay_range=(0.3, 0.6)):
                logger.info("Action: HIT")
            else:
                logger.warning("HIT button not found on screen")
        else:
            logger.warning("hit_button element not configured")

    def _click_stand(self) -> None:
        """Click the STAND button."""
        stand_button = self.get_element("stand_button")
        if stand_button:
            if click_element(stand_button, self.confidence, delay_range=(0.3, 0.6)):
                logger.info("Action: STAND")
            else:
                logger.warning("STAND button not found on screen")
        else:
            logger.warning("stand_button element not configured")

    def _click_double(self, fallback_hit: bool = True) -> None:
        """
        Click the DOUBLE button. If not available (e.g. after hitting),
        fall back to HIT.
        """
        double_button = self.get_element("double_button")
        if double_button:
            if click_element(double_button, self.confidence, delay_range=(0.3, 0.6)):
                logger.info("Action: DOUBLE")
                return

        # Double not available (only allowed on first two cards) — fall back
        if fallback_hit:
            logger.info("DOUBLE not available — falling back to HIT")
            self._click_hit()
        else:
            logger.warning("DOUBLE button not found and no fallback")

    # ── OCR Readers ──────────────────────────────────────────────────────

    def _read_player_total(self) -> Optional[int]:
        """Read the player's hand total via OCR."""
        region = self.get_region("player_total")
        if not region:
            return None

        value = read_number(region)
        if value is not None:
            total = int(value)
            logger.debug(f"Player total: {total}")
            return total
        return None

    def _read_dealer_total(self) -> Optional[int]:
        """Read the dealer's total via OCR."""
        region = self.get_region("dealer_total")
        if not region:
            return None

        value = read_number(region)
        if value is not None:
            upcard = int(value)
            # Face cards (J/Q/K) are worth 10, Ace = 11
            if upcard > 11:
                upcard = 10
            logger.debug(f"Dealer upcard: {upcard}")
            return upcard
        return None

    def _read_balance(self) -> Optional[float]:
        """Read current balance via OCR."""
        region = self.get_region("balance")
        if not region:
            return None

        balance = read_number(region)
        if balance is not None:
            logger.debug(f"Balance: ${balance:.2f}")
        return balance
