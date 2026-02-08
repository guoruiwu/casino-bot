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
python3 tools/capture.py --game crazy_time_dk --type crazy_time
```

4. It will ask for 2 things:
   - **betting_open**: select the corners of the "betting open" indicator
   - **bet positions**: type a segment name (e.g. `1`), hover over it, press Enter. Type `done` when finished.

### Slot Game

1. Open the slot on DraftKings/FanDuel in Chrome
2. Run:

```bash
cd /Users/guoruiwu/Github/casino-bot
python3 tools/capture.py --game GAME_NAME --type slot
```

3. It will ask you to capture the spin button (select corners)

---

## Run the Bot

### Crazy Time

1. Open Crazy Time on DraftKings in Chrome
2. Select your chip value (e.g. $1)
3. Run:

```bash
cd /Users/guoruiwu/Github/casino-bot
python3 main.py --config config/games/crazy_time_dk.yaml --duration 60
```

### Slot Game

1. Open the slot in Chrome
2. Set your bet to the minimum
3. Run:

```bash
cd /Users/guoruiwu/Github/casino-bot
python3 main.py --config config/games/GAME_NAME.yaml --duration 60
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
python3 tools/capture.py --game crazy_time_dk --reset --type crazy_time
```

This deletes the old screenshots and config, then walks you through capturing again.

To just delete without re-capturing:

```bash
python3 tools/capture.py --game crazy_time_dk --reset
```

---

## Cheat Sheet

| What | Command |
|------|---------|
| Set up Crazy Time | `python3 tools/capture.py --game crazy_time_dk --type crazy_time` |
| Set up a slot | `python3 tools/capture.py --game GAME_NAME --type slot` |
| Run Crazy Time 60 min | `python3 main.py --config config/games/crazy_time_dk.yaml --duration 60` |
| Run a slot 60 min | `python3 main.py --config config/games/GAME_NAME.yaml --duration 60` |
| Test assets on screen | `python3 tools/capture.py --game GAME_NAME --test` |
| Reset & re-capture | `python3 tools/capture.py --game GAME_NAME --reset --type crazy_time` |
| Stop | Ctrl+C |
