# Friday

A self-hosted AI work assistant that communicates through Slack DMs. Built on [Claude Code](https://claude.ai/code) + Python.

Friday polls your Slack DMs, processes messages using Claude, and responds — all running locally on your Mac. No server, no bot tokens, no admin access required.

## How It Works

```
You send a Slack DM to yourself
        ↓
message_bus.py polls every 60s (via claude --print)
        ↓
Claude reads your DMs using Slack MCP tools
        ↓
Claude generates a response as Friday
        ↓
Response posted back to your Slack DMs
        (prefixed with ⚙️ Friday: to prevent echo loops)
```

## Quick Start

1. **Clone the repo**
   ```bash
   git clone git@github.com:working-with-gage/friday.git ~/friday
   ```

2. **Open it in Claude Code**
   ```bash
   cd ~/friday
   claude
   ```

3. **Claude Code handles the rest.** It reads `CLAUDE.md`, detects that setup hasn't been completed, and walks you through configuration interactively — filling in your details, connecting Slack, creating the background service, and running a test.

That's it. No manual config editing required.

## What You Need

- **macOS** with Apple Silicon (M-series)
- **Claude Code** CLI installed ([install guide](https://docs.anthropic.com/en/docs/claude-code/overview))
- **Slack MCP** connected in Claude Code (via claude.ai settings or MCP config)
- **Python 3.9+** (included with macOS)

## Architecture

```
friday/
├── CLAUDE.md              # Setup + runtime instructions (Claude Code reads this)
├── SOUL.md                # Personality and tone
├── IDENTITY.md            # Name, emoji, vibe
├── USER.md                # Your details (filled in during setup)
├── MEMORY.md              # Long-term memory (Friday builds this over time)
├── AGENTS.md              # Workspace rules and behavior guidelines
├── WORKQUEUE.md           # Pending tasks
├── HEARTBEAT.md           # Recurring check definitions
├── TOOLS.md               # Environment-specific notes
├── .env.example           # Template for required env vars
├── scripts/
│   ├── message_bus.py     # Core: Slack DM polling + Claude processing loop
│   └── scheduler.py       # Heartbeat runner for proactive tasks
└── skills/
    └── browser/           # Headless Chromium (Playwright) for web tasks
        ├── browse.py
        └── browse
```

## Poll Schedule

| Time Window | Interval | Rationale |
|---|---|---|
| 10am – 4pm ET | Every 60 seconds | Active work hours — fast responses |
| Outside window | Every 60 minutes | Idle — conserve resources |

Configurable in `message_bus.py` (`ACTIVE_START`, `ACTIVE_END`, `POLL_ACTIVE`, `POLL_IDLE`).

## Echo Prevention

Since Slack MCP sends messages as *you* (not a bot), Friday needs to distinguish its own responses from your messages. It does this with:

1. **Prefix** — All Friday responses start with `⚙️ Friday:`. The polling prompt skips messages with this prefix.
2. **Timestamp tracking** — Processed message timestamps are saved to `.poll-state.json` to avoid reprocessing.
3. **Bot/noise filtering** — Messages starting with emojis, "Boxer", or containing "Sent using" are skipped.

## Customization

- **Personality**: Edit `SOUL.md` — tone, boundaries, communication style
- **Identity**: Edit `IDENTITY.md` — rename Friday to anything you want
- **Schedule**: Edit `POLL_ACTIVE` / `POLL_IDLE` / `ACTIVE_START` / `ACTIVE_END` in `message_bus.py`
- **Skills**: Add new skill directories under `skills/` with a `SKILL.md` describing the workflow

## Managing Friday

```bash
# Check status
launchctl list | grep friday

# View logs
tail -f ~/friday/friday.log

# Stop
launchctl unload ~/Library/LaunchAgents/com.friday.message-bus.plist

# Start
launchctl load ~/Library/LaunchAgents/com.friday.message-bus.plist

# Restart (after code changes)
launchctl unload ~/Library/LaunchAgents/com.friday.message-bus.plist
launchctl load ~/Library/LaunchAgents/com.friday.message-bus.plist
```

## Future Improvements

- **Slack bot token** — If you can get a bot installed (requires admin), swap MCP polling for direct API calls. Much more efficient.
- **Telegram/Discord** — Swap the Slack transport for any messaging platform.
- **More skills** — Add podcast generation, voice transcription, or anything else you need.

## License

MIT
