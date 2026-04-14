#!/usr/bin/env python3
"""
Friday — Scheduler
Handles heartbeats and proactive tasks. Sends alerts via Slack DMs
through Claude Code MCP tools.
"""

import json
import os
import subprocess
import time
import logging
from datetime import datetime
from pathlib import Path

# ── Config ──
WORKSPACE = Path.home() / "friday"
HEARTBEAT_INTERVAL = 1800  # 30 minutes
SLACK_USER_ID = os.environ.get("FRIDAY_SLACK_USER_ID", "")
FRIDAY_PREFIX = "⚙️ Friday:"

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(WORKSPACE / "scheduler.log"),
    ],
)
log = logging.getLogger("scheduler")


def call_claude(prompt: str, timeout: int = 180) -> str:
    """Call Claude Code in --print mode."""
    try:
        result = subprocess.run(
            ["claude", "--print", "--permission-mode", "bypassPermissions",
             "--output-format", "text", prompt],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(WORKSPACE),
        )
        return result.stdout.strip() if result.returncode == 0 else f"Error: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return "Timed out"
    except Exception as e:
        return f"Error: {e}"


def send_slack_dm(message: str):
    """Send a Slack DM via Claude Code MCP."""
    prompt = f"""Send this message via Slack DM.
Use slack_send_message with channel_id: "{SLACK_USER_ID}"
Message text (send exactly this): {FRIDAY_PREFIX} {message}

Do NOT add anything else. Just send the message."""

    call_claude(prompt, timeout=60)


def run_heartbeat():
    """Execute heartbeat check."""
    log.info("Running heartbeat...")

    heartbeat_md = ""
    workqueue_md = ""

    hb_file = WORKSPACE / "HEARTBEAT.md"
    if hb_file.exists():
        heartbeat_md = hb_file.read_text()

    wq_file = WORKSPACE / "WORKQUEUE.md"
    if wq_file.exists():
        workqueue_md = wq_file.read_text()

    prompt = f"""You are Friday. Read the following and take action if needed.

# HEARTBEAT.md
{heartbeat_md}

# WORKQUEUE.md
{workqueue_md}

Current time: {datetime.now().strftime('%A, %B %d, %Y — %I:%M %p')} ET

If there's pending work in WORKQUEUE.md (Status is not EMPTY/DONE), execute it.
If something needs attention, send a Slack DM using slack_send_message
with channel_id: "{SLACK_USER_ID}". ALWAYS prefix messages with "{FRIDAY_PREFIX} ".
If nothing needs attention, respond with exactly: HEARTBEAT_OK"""

    response = call_claude(prompt, timeout=180)

    if "HEARTBEAT_OK" in response:
        log.info("Heartbeat: OK — nothing needs attention")
    else:
        log.info(f"Heartbeat action taken: {response[:100]}...")


def main():
    log.info("=" * 50)
    log.info("Friday — Scheduler starting")
    log.info(f"Heartbeat interval: {HEARTBEAT_INTERVAL}s")
    log.info("=" * 50)

    last_heartbeat = 0

    while True:
        try:
            now = time.time()
            now_dt = datetime.now()

            # Heartbeat check
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                # Only run during work hours (7am-10pm ET)
                if 7 <= now_dt.hour <= 22:
                    run_heartbeat()
                else:
                    log.info("Outside work hours — skipping heartbeat")
                last_heartbeat = now

            time.sleep(30)

        except KeyboardInterrupt:
            log.info("Scheduler shutting down...")
            break
        except Exception as e:
            log.error(f"Scheduler error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
