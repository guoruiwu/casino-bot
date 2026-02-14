# Quick Start — Run Each Time

## Before First Use (One Time)

```bash
cd /Users/guoruiwu/Github/casino-bot
brew install tesseract
pip3 install -r requirements.txt
```

Grant permissions to your terminal app:
- System Settings > Privacy & Security > **Accessibility**
- System Settings > Privacy & Security > **Screen Recording**

---

## New Game Setup (Once Per Game)

### Crazy Time

1. Open Crazy Time on DraftKings in Chrome
2. Select your chip value in the game (e.g. $1)
3. Run:

```bash
cd /Users/guoruiwu/Github/casino-bot
python3 tools/capture.py --game crazy_time
```

4. It will ask for 2 things:
   - **betting_open**: select the corners of the "betting open" indicator
   - **bet positions**: type a segment name (e.g. `1`), hover over it, press Enter. Type `done` when finished.

### Slot Game

1. Open the slot on DraftKings/FanDuel in Chrome
2. Run:

```bash
cd /Users/guoruiwu/Github/casino-bot
python3 tools/capture.py --game slot
```

3. It will ask you to capture the spin button (select corners)

### Diamond Wild

1. Open Diamond Wild in Chrome
2. Run:

```bash
cd /Users/guoruiwu/Github/casino-bot
python3 tools/capture.py --game diamond_wild
```

3. It will ask for 2 things:
   - **spin_button** (required): select the corners of the spin button
   - **dismiss_popup** (optional): select the corners of the popup overlay that appears between spins — the bot clicks within this area to dismiss it

If you skip the popup during initial setup, you can add it later:

```bash
python3 tools/capture.py --game diamond_wild --update-asset dismiss_popup
```

---

## Update a Single Asset

If an asset needs re-capturing (e.g. the UI changed) or you want to add one you skipped earlier, use `--update-asset`:

```bash
cd /Users/guoruiwu/Github/casino-bot

# Re-capture the spin button for Diamond Wild
python3 tools/capture.py --game diamond_wild --update-asset spin_button

# Add the dismiss popup for Diamond Wild
python3 tools/capture.py --game diamond_wild --update-asset dismiss_popup

# Re-capture the spin button for a slot
python3 tools/capture.py --game slot --update-asset spin_button
```

This saves the new screenshot and adds the element to the YAML config if it's not already there. No need to re-run the full capture.

---

## Reality Check Popup (All Games)

Platforms sometimes show a "reality check" popup that pauses gameplay. The bot can automatically dismiss this for any game.

To set it up:

```bash
cd /Users/guoruiwu/Github/casino-bot

# For Diamond Wild
python3 tools/capture.py --game diamond_wild --update-asset reality_check

# For Crazy Time
python3 tools/capture.py --game crazy_time --update-asset reality_check

# For any slot
python3 tools/capture.py --game slot --update-asset reality_check
```

It will ask for 2 things:
1. **Screenshot region**: select the corners of something that identifies the popup (e.g. the title or a unique part of the dialog)
2. **Button position**: hover over the dismiss/continue button and press Enter

The bot checks for this popup before every action. If it appears, it clicks the button and resumes playing.

---

## Run the Bot

### Crazy Time

1. Open Crazy Time on DraftKings in Chrome
2. Select your chip value (e.g. $1)
3. Run:

```bash
cd /Users/guoruiwu/Github/casino-bot
python3 main.py --config config/games/crazy_time.yaml --duration 60
```

### Slot Game

1. Open the slot in Chrome
2. Set your bet to the minimum
3. Run:

```bash
cd /Users/guoruiwu/Github/casino-bot
python3 main.py --config config/games/slot.yaml --duration 60
```

### Diamond Wild

1. Open Diamond Wild in Chrome
2. Run:

```bash
cd /Users/guoruiwu/Github/casino-bot
python3 main.py --config config/games/diamond_wild.yaml --duration 60
```

Change `60` to however many minutes you want to play.

---

## Stop the Bot

Press **Ctrl+C**. It stops after the current action finishes.

---

## Reset a Game (Re-capture Screenshots & Positions)

If the game UI changed or your positions are wrong:

```bash
cd /Users/guoruiwu/Github/casino-bot
python3 tools/capture.py --game crazy_time --reset
```

This deletes the old screenshots and config, then walks you through capturing again.

To just delete without re-capturing:

```bash
python3 tools/capture.py --game crazy_time --reset
```

---

## Cheat Sheet

| What | Command |
|------|---------|
| Set up Crazy Time | `python3 tools/capture.py --game crazy_time` |
| Set up a slot | `python3 tools/capture.py --game slot` |
| Set up Diamond Wild | `python3 tools/capture.py --game diamond_wild` |
| Update one asset | `python3 tools/capture.py --game slot --update-asset ELEMENT` |
| Set up reality check | `python3 tools/capture.py --game slot --update-asset reality_check` |
| Run Crazy Time 60 min | `python3 main.py --config config/games/crazy_time.yaml --duration 60` |
| Run a slot 60 min | `python3 main.py --config config/games/slot.yaml --duration 60` |
| Run Diamond Wild 60 min | `python3 main.py --config config/games/diamond_wild.yaml --duration 60` |
| Test assets on screen | `python3 tools/capture.py --game slot --test` |
| Reset & re-capture | `python3 tools/capture.py --game slot --reset` |
| Stop | Ctrl+C |
