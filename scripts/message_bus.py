#!/usr/bin/env python3
"""
Friday — Slack Message Bus
Polls Slack DMs via Claude Code MCP tools, processes messages,
and sends replies back through Slack.

Architecture:
  Every POLL_INTERVAL seconds, this script calls `claude --print` with a prompt
  that instructs Claude to:
    1. Read Slack DMs using the MCP slack_read_channel tool
    2. Identify new messages (after last_ts) that aren't Friday's own responses
    3. If new messages exist, process and respond via MCP slack_send_message
    4. Output a state line (FRIDAY_POLL:{...}) for this script to parse

  Echo prevention:
    - All Friday responses are prefixed with "⚙️ Friday: "
    - The polling prompt instructs Claude to skip messages with that prefix
    - Sent message timestamps are tracked as a secondary safeguard
"""

import json
import os
import sys
import time
import subprocess
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ──
WORKSPACE = Path.home() / "friday"
SLACK_USER_ID = os.environ.get("FRIDAY_SLACK_USER_ID", "")
FRIDAY_PREFIX = "⚙️ Friday:"
STATE_FILE = WORKSPACE / ".poll-state.json"

# Poll intervals (seconds)
POLL_ACTIVE = 60       # 10am-4pm ET: every minute
POLL_IDLE = 3600       # Outside work hours: every hour
ACTIVE_START = 10      # 10:00 AM ET
ACTIVE_END = 16        # 4:00 PM ET


def get_poll_interval() -> int:
    """Return poll interval based on current ET hour."""
    hour = datetime.now().hour  # machine is in ET
    if ACTIVE_START <= hour < ACTIVE_END:
        return POLL_ACTIVE
    return POLL_IDLE

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(WORKSPACE / "friday.log"),
    ],
)
log = logging.getLogger("friday")


# ── State Management ──

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            log.warning("Corrupt state file, resetting")
    return {"last_ts": None, "initialized": False}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Context Building ──

def build_context() -> str:
    """Build system context from workspace identity/memory files."""
    parts = []

    for filename in ["SOUL.md", "USER.md", "IDENTITY.md"]:
        filepath = WORKSPACE / filename
        if filepath.exists():
            parts.append(f"# {filename}\n{filepath.read_text()}")

    memory_file = WORKSPACE / "MEMORY.md"
    if memory_file.exists():
        parts.append(f"# MEMORY.md\n{memory_file.read_text()}")

    # Today + yesterday daily logs
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    for date_str in [yesterday, today]:
        daily = WORKSPACE / "memory" / f"{date_str}.md"
        if daily.exists():
            content = daily.read_text()
            if len(content) > 3000:
                content = content[:3000] + "\n... (truncated)"
            parts.append(f"# memory/{date_str}.md\n{content}")

    wq = WORKSPACE / "WORKQUEUE.md"
    if wq.exists():
        parts.append(f"# WORKQUEUE.md\n{wq.read_text()}")

    return "\n\n---\n\n".join(parts)


# ── Claude Code Integration ──

def call_claude_poll(system_context: str, last_ts: str) -> str:
    """Call Claude Code to check Slack DMs and respond if needed."""

    oldest_param = f', oldest: "{last_ts}"' if last_ts else ""

    full_prompt = f"""You are Friday, a work AI assistant. You communicate via Slack DMs.

{system_context}

---

## Your Task Right Now

Check Slack DMs for new messages and respond if needed.

### Step 1: Read DMs
Use the slack_read_channel tool with channel_id: "{SLACK_USER_ID}"{oldest_param}, limit: 15

### Step 2: Filter Messages
Look at the returned messages. SKIP any message that matches ANY of these:
- Starts with "{FRIDAY_PREFIX}" — those are your own previous responses
- Starts with an emoji (any Slack emoji like :boxing_glove:, :sunny:, :gear:, :warning:, etc.)
- Starts with "Boxer" or "*Boxer" — those are automated agent messages
- Contains "Sent using" near the end — automated bot output
- Is a bot message

Only process messages that look like genuine, direct messages from the user.

### Step 3: Respond (if new messages exist)
If there are genuine messages that pass the filters above:
- Read and understand them
- Compose a response as Friday — direct, helpful, professional
- Send your response via slack_send_message with channel_id: "{SLACK_USER_ID}"
- **CRITICAL: Your message text MUST start with "{FRIDAY_PREFIX} "** (including the space after the colon)
- If there are multiple new messages, address them all in a single response

### Step 4: Report State
On the VERY LAST line of your output, print exactly one of:
- If you responded: FRIDAY_POLL:{{"last_ts":"<timestamp of the newest message you saw>","responded":true}}
- If no new messages: FRIDAY_POLL:{{"last_ts":"{last_ts or ''}","responded":false}}

### Rules
- ALWAYS prefix Slack messages with "{FRIDAY_PREFIX} " — this prevents echo loops
- Do NOT respond to your own messages (anything starting with "{FRIDAY_PREFIX}")
- Keep responses Slack-appropriate — concise unless depth is warranted
- If you see no messages at all or only your own messages, just report state and stop"""

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--permission-mode", "bypassPermissions",
                "--output-format", "text",
                full_prompt,
            ],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(WORKSPACE),
        )

        if result.returncode != 0:
            log.error(f"Claude Code error (rc={result.returncode}): {result.stderr[:500]}")
            return ""

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        log.error("Claude Code timed out (300s)")
        return ""
    except FileNotFoundError:
        log.error("Claude Code CLI not found — is 'claude' in PATH?")
        sys.exit(1)
    except Exception as e:
        log.error(f"Claude Code call failed: {e}")
        return ""


def call_claude_init() -> str:
    """Initialization call — just read the latest DM timestamp without responding."""

    prompt = f"""Read Slack DMs using slack_read_channel with channel_id: "{SLACK_USER_ID}", limit: 1

Look at the most recent message. Report its timestamp.

On the VERY LAST line of your output, print:
FRIDAY_POLL:{{"last_ts":"<timestamp of newest message>","responded":false}}

If the channel is empty:
FRIDAY_POLL:{{"last_ts":"","responded":false}}

Do NOT send any messages. This is just initialization."""

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--permission-mode", "bypassPermissions",
                "--output-format", "text",
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(WORKSPACE),
        )

        if result.returncode != 0:
            log.error(f"Init call error: {result.stderr[:500]}")
            return ""

        return result.stdout.strip()

    except Exception as e:
        log.error(f"Init call failed: {e}")
        return ""


def parse_poll_result(output: str) -> dict:
    """Parse the FRIDAY_POLL state from Claude's output."""
    for line in reversed(output.split("\n")):
        line = line.strip()
        if line.startswith("FRIDAY_POLL:"):
            try:
                json_str = line[len("FRIDAY_POLL:"):]
                return json.loads(json_str)
            except json.JSONDecodeError:
                log.warning(f"Failed to parse poll JSON: {line}")

    log.warning("No FRIDAY_POLL line found in output")
    return {"last_ts": None, "responded": False}


# ── Main Loop ──

def main():
    if not SLACK_USER_ID:
        log.error("FRIDAY_SLACK_USER_ID not set. Export it or add to .env")
        sys.exit(1)

    log.info("=" * 50)
    log.info("Friday — Slack Message Bus starting")
    log.info(f"Workspace: {WORKSPACE}")
    log.info(f"Active hours: {ACTIVE_START}:00-{ACTIVE_END}:00 ET → {POLL_ACTIVE}s poll")
    log.info(f"Idle hours: outside window → {POLL_IDLE}s poll")
    log.info(f"Slack User ID: {SLACK_USER_ID}")
    log.info("=" * 50)

    state = load_state()

    # First run: initialize by reading latest timestamp without responding
    if not state.get("initialized"):
        log.info("First run — initializing timestamp from Slack...")
        output = call_claude_init()
        if output:
            poll_result = parse_poll_result(output)
            if poll_result.get("last_ts"):
                state["last_ts"] = poll_result["last_ts"]
                state["initialized"] = True
                save_state(state)
                log.info(f"Initialized. last_ts: {state['last_ts']}")
            else:
                log.info("No messages found in DM — starting fresh")
                state["initialized"] = True
                save_state(state)
        else:
            log.error("Init failed — will retry next cycle")

    log.info(f"Polling starts. last_ts: {state.get('last_ts', 'none')}")

    while True:
        try:
            interval = get_poll_interval()
            log.info(f"Polling... (interval: {interval}s, last_ts: {state.get('last_ts', 'none')})")

            system_context = build_context()
            output = call_claude_poll(system_context, state.get("last_ts"))

            if output:
                poll_result = parse_poll_result(output)

                if poll_result.get("responded"):
                    log.info(f"Responded to new messages. last_ts → {poll_result.get('last_ts')}")
                else:
                    log.info("No new messages.")

                if poll_result.get("last_ts"):
                    state["last_ts"] = poll_result["last_ts"]
                    save_state(state)
            else:
                log.warning("Empty Claude output — skipping this cycle")

            time.sleep(interval)

        except KeyboardInterrupt:
            log.info("Shutting down gracefully...")
            break
        except Exception as e:
            log.error(f"Main loop error: {e}")
            time.sleep(30)


if __name__ == "__main__":
    main()
