# Casino Leaderboard Bot

A Python screen-automation bot for playing casino leaderboard games (slots and live games) on FanDuel and DraftKings in Chrome on macOS.

Uses **image matching** (OpenCV template matching) to find UI elements and **OCR** (Tesseract) to read dynamic text like balances and bet amounts. Games are defined in YAML config files for fast weekly updates.

## Setup

### Prerequisites

- Python 3.11+
- macOS with Chrome browser
- Homebrew

### Install System Dependencies

```bash
brew install tesseract
```

### Install Python Dependencies

```bash
cd casino-bot
pip3 install -r requirements.txt
```

### Grant macOS Permissions

The bot needs two macOS permissions (grant to your terminal app):

1. **Accessibility** — System Settings > Privacy & Security > Accessibility
2. **Screen Recording** — System Settings > Privacy & Security > Screen Recording

## Usage

### 1. Capture Game Assets (First Time per Game)

Open the game in Chrome, then run:

```bash
# For a slot game
python3 tools/capture.py --game my_slot_dk --type slot

# For Crazy Time Live
python3 tools/capture.py --game crazy_time_dk --type crazy_time
```

The tool walks you through screenshotting each UI element (spin button, bet controls, bonus indicators, etc.) and generates a starter YAML config.

### 2. Test Assets

Verify all captured assets can be found on the current screen:

```bash
python3 tools/capture.py --test my_slot_dk
```

### 3. Run the Bot

```bash
# Run for 60 minutes (default)
python3 main.py --config config/games/my_slot_dk.yaml

# Run for a custom duration
python3 main.py --config config/games/my_slot_dk.yaml --duration 90
```

### 4. Stop the Bot

Press `Ctrl+C` to gracefully stop after the current action completes.

## New Computer Setup

Assets (screenshots) and game configs contain screen coordinates and pixel data that are specific to each machine's display resolution. When moving to a new computer:

```bash
# 1. Install dependencies
brew install tesseract
pip3 install -r requirements.txt

# 2. Grant macOS permissions (Accessibility + Screen Recording)

# 3. Re-capture assets for each game you want to run
python3 tools/capture.py --game crazy_time_dk --type crazy_time
```

To reset and re-capture an existing game (e.g. if the UI changed):

```bash
python3 tools/capture.py --game crazy_time_dk --reset --type crazy_time
```

## Weekly Update Workflow

When a new leaderboard game drops:

1. Open the game in Chrome
2. `python3 tools/capture.py --game <name> --type slot`
3. Screenshot each UI element (tool walks you through it)
4. Edit the generated YAML config if needed (bet amount, regions, thresholds)
5. `python3 main.py --config config/games/<name>.yaml --duration 60`

~5 minutes to set up a new slot game. No code changes needed.

## Slot Spin Modes

- **Manual** (`spin_mode: manual`) — Bot clicks spin each time. Default, works everywhere.
- **Autoplay** (`spin_mode: autoplay`) — Bot activates built-in autoplay, monitors for bonus rounds and session end.

Set `spin_mode` in the game's YAML config.

## Project Structure

```
casino-bot/
├── config/games/         # YAML game definitions (machine-specific, not committed)
├── assets/               # Screenshot snippets of UI elements per game (not committed)
├── src/
│   ├── screen.py         # Screenshot, image matching, OCR
│   ├── actions.py        # Click, jitter, delay wrappers
│   └── games/
│       ├── base_game.py  # Abstract base class
│       ├── slots.py      # Generic slot runner
│       └── crazy_time.py # Crazy Time Live runner
├── tools/
│   └── capture.py        # Asset capture CLI
└── main.py               # Entry point
```

## Leaderboard Strategy

This bot targets **Money Multiplier** leaderboards (win-to-wager ratio). It plays at minimum bet to maximize the ratio when wins land. No early stopping — run for the session duration.
