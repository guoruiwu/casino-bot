"""
Diamond Wild game runner.

Simple spin-based game — detects when the spin button is ready and clicks it.
No bet management or bonus round handling needed.
"""

from __future__ import annotations

import logging
import time
from enum import Enum

from src.actions import click_element, click_position, move_mouse_away, random_delay
from src.games.base_game import BaseGame
from src.screen import find_element, take_screenshot

logger = logging.getLogger(__name__)


class DiamondWildState(str, Enum):
    """States for the Diamond Wild state machine."""

    READY = "ready"          # Spin button visible — ready to spin
    WAITING = "waiting"      # Spin in progress or transition — wait for spin button
    DISMISS = "dismiss"      # Popup on screen — click anywhere to dismiss


class DiamondWildGame(BaseGame):
    """
    Diamond Wild game runner.

    Simple two-state loop:
      1. Detect spin button on screen  → READY
      2. Click it, wait for it to reappear → WAITING
    """

    def __init__(self, config_path):
        super().__init__(config_path)

        self.spin_wait = self.settings.get("spin_wait", 1.0)
        self.poll_interval = self.settings.get("poll_interval", 1.0)

        logger.info("Diamond Wild game loaded")

    # ── State Detection ──────────────────────────────────────────────────

    def detect_state(self) -> str:
        """Check if the spin button is visible on screen."""
        screenshot = take_screenshot()

        # Check for dismiss popup first (higher priority)
        dismiss = self.get_element("dismiss_popup")
        if dismiss and find_element(dismiss, self.confidence, screenshot=screenshot):
            return DiamondWildState.DISMISS

        spin_btn = self.get_element("spin_button")
        if spin_btn and find_element(spin_btn, self.confidence, screenshot=screenshot):
            return DiamondWildState.READY

        return DiamondWildState.WAITING

    # ── Step Execution ───────────────────────────────────────────────────

    def step(self, state: str) -> None:
        """Execute one step based on current state."""
        if state == DiamondWildState.DISMISS:
            self._step_dismiss()
        elif state == DiamondWildState.READY:
            self._step_spin()
        else:
            self._step_wait()

    def _step_spin(self) -> None:
        """Click the spin button."""
        spin_btn = self.get_element("spin_button")
        if not spin_btn:
            logger.error("Spin button element not configured!")
            time.sleep(2)
            return

        if click_element(spin_btn, self.confidence, delay_range=self.action_delay):
            logger.info("Spin clicked")
            move_mouse_away()
            self.log_round(notes="spin")
            # Wait for the spin animation to play out
            time.sleep(self.spin_wait)
        else:
            logger.warning("Spin button detected but click failed — retrying")
            time.sleep(1)

    def _step_dismiss(self) -> None:
        """Click within the popup boundary to dismiss it."""
        logger.info("Popup detected — clicking to dismiss")
        dismiss = self.get_element("dismiss_popup")
        if dismiss:
            click_element(dismiss, self.confidence, jitter=True, delay_range=(0.5, 1.0))
        else:
            logger.warning("dismiss_popup element not configured")
            random_delay(0.5, 1.0)

    def _step_wait(self) -> None:
        """Wait for the spin button to reappear."""
        logger.debug("Waiting for spin button...")
        time.sleep(self.poll_interval)
