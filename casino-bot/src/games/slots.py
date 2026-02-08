"""
Generic slot machine game runner.

Supports two spin modes:
  - manual: bot clicks spin each time
  - autoplay: bot activates game's built-in autoplay and monitors

Handles bonus rounds: free spins, pick-and-click, and wheel bonuses.
"""

from __future__ import annotations

import logging
import random
import time
from enum import Enum

from src.actions import (
    click_element,
    click_all_elements,
    click_position,
    click_region_random,
    move_mouse_away,
    random_delay,
)
from src.games.base_game import BaseGame
from src.screen import (
    element_exists,
    find_element,
    find_all_elements,
    read_number,
    take_screenshot,
    wait_for_any_element,
    wait_for_element,
)

logger = logging.getLogger(__name__)


class SlotState(str, Enum):
    """Possible states for the slot state machine."""

    SET_BET = "set_bet"
    SPIN = "spin"
    SPINNING = "spinning"
    ROUND_RESULT = "round_result"
    BONUS_FREE_SPINS = "bonus_free_spins"
    BONUS_PICK = "bonus_pick"
    BONUS_WHEEL = "bonus_wheel"
    # Autoplay-specific states
    START_AUTOPLAY = "start_autoplay"
    MONITORING = "monitoring"
    RESUME_AUTOPLAY = "resume_autoplay"
    # Meta
    UNKNOWN = "unknown"


class SlotsGame(BaseGame):
    """Generic slot machine runner that works with any slot via YAML config."""

    def __init__(self, config_path):
        super().__init__(config_path)

        # Slot-specific config
        self.spin_mode = self.config.get("spin_mode", "manual")
        self.target_bet = self.settings.get("target_bet", 0.20)
        self.spin_wait = self.settings.get("spin_wait", 3.0)
        self.poll_interval = self.settings.get("poll_interval", 2.0)

        # Autoplay config
        autoplay_cfg = self.config.get("autoplay", {})
        self.autoplay_num_spins = autoplay_cfg.get("num_spins", 100)

        # State tracking
        self.bet_is_set = False
        self.autoplay_active = False
        self._last_balance_check = 0.0
        self._balance_check_interval = 30.0  # seconds

        logger.info(f"Spin mode: {self.spin_mode}")
        logger.info(f"Target bet: ${self.target_bet:.2f}")

    def on_start(self) -> None:
        """Read initial balance on session start."""
        balance = self._read_balance()
        if balance is not None:
            self.starting_balance = balance
            self.current_balance = balance
            logger.info(f"Starting balance: ${balance:.2f}")

    def on_stop(self) -> None:
        """Cancel autoplay if active, read final balance."""
        if self.autoplay_active:
            self._cancel_autoplay()

        balance = self._read_balance()
        if balance is not None:
            self.current_balance = balance

    # ── State Detection ──────────────────────────────────────────────────

    def detect_state(self) -> str:
        """Determine current slot game state from the screen."""
        screenshot = take_screenshot()

        # Check for bonus rounds first (highest priority)
        bonus_state = self._detect_bonus(screenshot)
        if bonus_state:
            return bonus_state

        # Autoplay mode state detection
        if self.spin_mode == "autoplay":
            return self._detect_autoplay_state(screenshot)

        # Manual mode state detection
        return self._detect_manual_state(screenshot)

    def _detect_manual_state(self, screenshot) -> str:
        """State detection for manual spin mode."""
        # Check if spin button is visible (ready for next spin)
        spin_btn = self.get_element("spin_button")
        if spin_btn and find_element(spin_btn, self.confidence, screenshot=screenshot):
            if not self.bet_is_set:
                return SlotState.SET_BET
            return SlotState.SPIN

        # If spin button not visible, we're likely mid-spin or in a result screen
        return SlotState.SPINNING

    def _detect_autoplay_state(self, screenshot) -> str:
        """State detection for autoplay mode."""
        # Check if autoplay is currently active
        autoplay_active_el = self.get_element("autoplay_active")
        if autoplay_active_el and find_element(
            autoplay_active_el, self.confidence, screenshot=screenshot
        ):
            self.autoplay_active = True
            return SlotState.MONITORING

        # Check if we can start autoplay (spin button / autoplay button visible)
        autoplay_btn = self.get_element("autoplay_button")
        if autoplay_btn and find_element(
            autoplay_btn, self.confidence, screenshot=screenshot
        ):
            if not self.bet_is_set:
                return SlotState.SET_BET
            if not self.autoplay_active:
                return SlotState.START_AUTOPLAY
            return SlotState.RESUME_AUTOPLAY

        # Spin button visible means autoplay stopped
        spin_btn = self.get_element("spin_button")
        if spin_btn and find_element(spin_btn, self.confidence, screenshot=screenshot):
            if not self.bet_is_set:
                return SlotState.SET_BET
            self.autoplay_active = False
            return SlotState.RESUME_AUTOPLAY

        # Otherwise we're in some transition state
        return SlotState.MONITORING

    def _detect_bonus(self, screenshot) -> str | None:
        """Check if any bonus round is active."""
        bonus_pick = self.get_element("bonus_pick")
        if bonus_pick and find_element(
            bonus_pick, self.confidence, screenshot=screenshot
        ):
            return SlotState.BONUS_PICK

        bonus_free = self.get_element("bonus_free_spins")
        if bonus_free and find_element(
            bonus_free, self.confidence, screenshot=screenshot
        ):
            return SlotState.BONUS_FREE_SPINS

        bonus_wheel = self.get_element("bonus_wheel")
        if bonus_wheel and find_element(
            bonus_wheel, self.confidence, screenshot=screenshot
        ):
            return SlotState.BONUS_WHEEL

        return None

    # ── Step Execution ───────────────────────────────────────────────────

    def step(self, state: str) -> None:
        """Execute one step based on current state."""
        handlers = {
            SlotState.SET_BET: self._step_set_bet,
            SlotState.SPIN: self._step_spin,
            SlotState.SPINNING: self._step_spinning,
            SlotState.ROUND_RESULT: self._step_round_result,
            SlotState.BONUS_FREE_SPINS: self._step_bonus_free_spins,
            SlotState.BONUS_PICK: self._step_bonus_pick,
            SlotState.BONUS_WHEEL: self._step_bonus_wheel,
            SlotState.START_AUTOPLAY: self._step_start_autoplay,
            SlotState.MONITORING: self._step_monitoring,
            SlotState.RESUME_AUTOPLAY: self._step_resume_autoplay,
        }

        handler = handlers.get(state, self._step_unknown)
        handler()

    # ── Manual Mode Steps ────────────────────────────────────────────────

    def _step_set_bet(self) -> None:
        """Ensure the bet is set to the target amount."""
        logger.info(f"Setting bet to ${self.target_bet:.2f}")

        # Try reading current bet amount via OCR
        bet_region = self.get_region("bet_amount")
        if bet_region:
            current_bet = read_number(bet_region)
            if current_bet is not None:
                logger.info(f"Current bet: ${current_bet:.2f}")
                if abs(current_bet - self.target_bet) < 0.01:
                    logger.info("Bet already correct")
                    self.bet_is_set = True
                    return

        # Try to adjust bet using up/down buttons
        # Strategy: click bet_down many times to go to minimum, then adjust up if needed
        bet_down = self.get_element("bet_down")
        if bet_down:
            logger.info("Clicking bet down to reach minimum...")
            for _ in range(20):  # Click down enough times to reach minimum
                if not click_element(bet_down, self.confidence, delay_range=(0.1, 0.2)):
                    break

            # Now check if we need to go up
            if bet_region:
                current_bet = read_number(bet_region)
                if current_bet is not None and current_bet < self.target_bet:
                    bet_up = self.get_element("bet_up")
                    if bet_up:
                        for _ in range(50):  # Safety limit
                            current_bet = read_number(bet_region)
                            if current_bet is not None and current_bet >= self.target_bet:
                                break
                            click_element(bet_up, self.confidence, delay_range=(0.1, 0.2))

        self.bet_is_set = True
        random_delay(0.3, 0.5)

        # Verify final bet
        if bet_region:
            final_bet = read_number(bet_region)
            if final_bet is not None:
                logger.info(f"Bet set to: ${final_bet:.2f}")

    def _step_spin(self) -> None:
        """Click the spin button for a manual spin."""
        spin_btn = self.get_element("spin_button")
        if not spin_btn:
            logger.error("Spin button not configured!")
            time.sleep(2)
            return

        if click_element(spin_btn, self.confidence, delay_range=self.action_delay):
            logger.debug("Spin clicked")
            move_mouse_away()
            # Wait for spin to complete
            time.sleep(self.spin_wait)
            self._check_round_result()
        else:
            logger.warning("Could not find spin button")
            time.sleep(1)

    def _step_spinning(self) -> None:
        """Wait for spinning to finish (spin button to reappear)."""
        spin_btn = self.get_element("spin_button")
        if spin_btn:
            # Wait up to 15 seconds for spin button to reappear
            pos = wait_for_element(spin_btn, self.confidence, timeout=15, poll_interval=1)
            if pos:
                self._check_round_result()
                return

        # Fallback: just wait
        time.sleep(2)

    def _check_round_result(self) -> None:
        """Check balance and log round after a spin."""
        # Periodic balance check
        now = time.time()
        if now - self._last_balance_check > self._balance_check_interval:
            balance = self._read_balance()
            self.log_round(balance=balance)
            self._last_balance_check = now
        else:
            self.log_round()

        # Small random delay between spins for human-like pacing
        random_delay(*self.action_delay)

    # ── Autoplay Mode Steps ──────────────────────────────────────────────

    def _step_start_autoplay(self) -> None:
        """Activate the game's autoplay feature."""
        logger.info("Starting autoplay...")

        autoplay_btn = self.get_element("autoplay_button")
        if not autoplay_btn:
            logger.error("Autoplay button not configured — falling back to manual mode")
            self.spin_mode = "manual"
            return

        if not click_element(autoplay_btn, self.confidence, delay_range=(0.5, 1.0)):
            logger.warning("Could not click autoplay button")
            time.sleep(2)
            return

        # Wait for autoplay dialog/confirmation
        time.sleep(1)

        # Click confirm/start button
        autoplay_confirm = self.get_element("autoplay_confirm")
        if autoplay_confirm:
            click_element(autoplay_confirm, self.confidence, delay_range=(0.3, 0.8))

        self.autoplay_active = True
        move_mouse_away()
        logger.info("Autoplay started")
        time.sleep(2)

    def _step_monitoring(self) -> None:
        """Monitor autoplay — check for bonuses and balance."""
        # Periodic balance check
        now = time.time()
        if now - self._last_balance_check > self._balance_check_interval:
            balance = self._read_balance()
            if balance is not None:
                self.current_balance = balance
            self._last_balance_check = now
            self.log_round(balance=balance, notes="autoplay")

        # Just poll and wait
        time.sleep(self.poll_interval)

    def _step_resume_autoplay(self) -> None:
        """Re-activate autoplay after it paused (e.g. after bonus round)."""
        logger.info("Resuming autoplay...")
        random_delay(1.0, 2.0)
        self._step_start_autoplay()

    def _cancel_autoplay(self) -> None:
        """Cancel active autoplay."""
        autoplay_stop = self.get_element("autoplay_stop")
        if autoplay_stop:
            logger.info("Cancelling autoplay...")
            click_element(autoplay_stop, self.confidence, delay_range=(0.3, 0.5))
            self.autoplay_active = False
            time.sleep(1)

    # ── Bonus Round Handlers ─────────────────────────────────────────────

    def _step_bonus_free_spins(self) -> None:
        """
        Handle free spins bonus round.

        Most games auto-spin during free spins. We just wait for the
        normal game UI to return.
        """
        logger.info("BONUS: Free Spins detected!")

        # Wait for free spins to complete — look for spin button to reappear
        spin_btn = self.get_element("spin_button")
        autoplay_btn = self.get_element("autoplay_button")

        # Build detection targets
        targets = {}
        if spin_btn:
            targets["spin_button"] = spin_btn
        if autoplay_btn:
            targets["autoplay_button"] = autoplay_btn

        if targets:
            # Free spins can take a while — long timeout
            result = wait_for_any_element(
                targets, self.confidence, timeout=120, poll_interval=2
            )
            if result:
                logger.info(f"Free spins complete (detected: {result[0]})")
        else:
            # Fallback: just wait a generous amount
            logger.info("Waiting for free spins to complete...")
            time.sleep(30)

        self._check_round_result()
        logger.info("Free spins bonus finished")

    def _step_bonus_pick(self) -> None:
        """
        Handle pick-and-click bonus round.

        Click items until the bonus ends (collect indicator appears or
        normal game UI returns).
        """
        logger.info("BONUS: Pick-and-Click detected!")
        random_delay(1.0, 2.0)

        pick_target = self.get_element("pick_target")
        pick_collect = self.get_element("pick_collect")
        spin_btn = self.get_element("spin_button")

        max_picks = 20  # Safety limit
        picks_made = 0

        for _ in range(max_picks):
            if not self.running:
                break

            # Check if bonus is over
            if pick_collect and element_exists(pick_collect, self.confidence):
                logger.info("Pick bonus: collect/end detected")
                # Click the collect button if needed
                click_element(pick_collect, self.confidence, delay_range=(0.5, 1.0))
                break

            if spin_btn and element_exists(spin_btn, self.confidence):
                logger.info("Pick bonus: normal game UI returned")
                break

            # Click a pick target
            if pick_target:
                positions = find_all_elements(pick_target, self.confidence)
                if positions:
                    # Pick a random item
                    x, y = random.choice(positions)
                    click_position(x, y, jitter=True, delay_range=(0.8, 1.5))
                    picks_made += 1
                    logger.info(f"Pick #{picks_made} at ({x}, {y})")
                else:
                    # No targets visible — might be animating
                    time.sleep(1)
            else:
                # No pick target configured — try clicking random area
                pick_region = self.get_region("pick_area")
                if pick_region:
                    click_region_random(pick_region)
                    picks_made += 1
                    random_delay(0.8, 1.5)
                else:
                    time.sleep(1)

        self._check_round_result()
        logger.info(f"Pick bonus finished ({picks_made} picks)")

    def _step_bonus_wheel(self) -> None:
        """
        Handle wheel bonus round.

        Click to spin the wheel, then wait for result.
        """
        logger.info("BONUS: Wheel detected!")
        random_delay(1.0, 2.0)

        # Try clicking the wheel or a spin button on it
        bonus_wheel = self.get_element("bonus_wheel")
        spin_btn = self.get_element("spin_button")

        # Click to spin the wheel
        if bonus_wheel:
            click_element(bonus_wheel, self.confidence, delay_range=(0.5, 1.0))

        # Wait for wheel to finish — look for normal game UI
        targets = {}
        if spin_btn:
            targets["spin_button"] = spin_btn
        autoplay_btn = self.get_element("autoplay_button")
        if autoplay_btn:
            targets["autoplay_button"] = autoplay_btn

        if targets:
            result = wait_for_any_element(
                targets, self.confidence, timeout=30, poll_interval=2
            )
            if result:
                logger.info(f"Wheel bonus complete (detected: {result[0]})")
        else:
            time.sleep(10)

        self._check_round_result()
        logger.info("Wheel bonus finished")

    # ── Utilities ────────────────────────────────────────────────────────

    def _step_unknown(self) -> None:
        """Handle unknown/transitional state — wait and retry."""
        logger.debug("Unknown state — waiting...")
        time.sleep(self.poll_interval)

    def _read_balance(self) -> float | None:
        """Read the current balance from screen via OCR."""
        balance_region = self.get_region("balance")
        if not balance_region:
            return None

        balance = read_number(balance_region)
        if balance is not None:
            logger.debug(f"Balance: ${balance:.2f}")
        return balance
