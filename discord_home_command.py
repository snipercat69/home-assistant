#!/usr/bin/env python3
"""Discord-friendly natural language wrapper for Home Assistant commands."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HA_SCRIPT = "/home/guy/.openclaw/workspace/scripts/integrations/home_assistant.py"
DEFAULT_LIGHT_ALIAS = "living_room_lights"


def run_ha(*args: str) -> dict:
    cmd = ["python3", HA_SCRIPT, *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "Home Assistant command failed").strip())
    out = (proc.stdout or "").strip()
    if not out:
        return {}
    try:
        return json.loads(out)
    except Exception:
        return {"raw": out}


def parse(message: str) -> tuple[str, dict]:
    text = message.strip().lower()
    if text.startswith("!home"):
        text = text[len("!home") :].strip()

    # destructive/security-sensitive actions must be explicitly confirmed first
    if any(k in text for k in ["unlock", "disarm", "disable alarm", "open garage", "open door"]):
        return "confirm_required", {"text": text}

    if "good night" in text:
        return "good_night", {}

    if any(k in text for k in ["temperature", "temp", "climate"]) and "set" not in text:
        return "temperature", {}

    if any(k in text for k in ["front door", "door locked", "is the door locked", "door status"]):
        return "front_door", {}

    if any(k in text for k in ["what devices are on", "devices on", "what's on", "whats on", "on right now"]):
        return "devices_on", {}

    m_set = re.search(r"set\s+([a-z0-9_\-\s]+?)\s+lights?\s+to\s+(\d{1,3})\s*%", text)
    if m_set:
        room = m_set.group(1).strip().replace(" ", "_")
        brightness = max(0, min(100, int(m_set.group(2))))
        return "light_set", {"target": f"{room}_lights", "brightness": brightness}

    m_off = re.search(r"turn\s+off\s+(?:the\s+)?([a-z0-9_\-\s]+?)?\s*lights?", text)
    if m_off:
        room = (m_off.group(1) or "").strip()
        target = DEFAULT_LIGHT_ALIAS if not room else f"{room.replace(' ', '_')}_lights"
        return "light_off", {"target": target}

    m_on = re.search(r"turn\s+on\s+(?:the\s+)?([a-z0-9_\-\s]+?)?\s*lights?", text)
    if m_on:
        room = (m_on.group(1) or "").strip()
        target = DEFAULT_LIGHT_ALIAS if not room else f"{room.replace(' ', '_')}_lights"
        return "light_on", {"target": target}

    return "unknown", {"text": text}


def fmt_temperature(data: dict) -> str:
    return (
        f"🌡️ Temp: {data.get('temperature')}°F, Humidity: {data.get('humidity')}%, "
        f"Climate: {data.get('climate_state')} (target {data.get('climate_target')}°F)"
    )


def fmt_front_door(data: dict) -> str:
    state = str(data.get("state", "unknown"))
    return f"🚪 Front door status: {state} ({data.get('entity_id')})"


def fmt_devices_on(data: dict) -> str:
    rows = data.get("active_devices", [])[:8]
    if not rows:
        return "✅ No active devices found right now."
    bits = [f"- {r.get('friendly_name')} ({r.get('state')})" for r in rows]
    return "⚡ Active devices:\n" + "\n".join(bits)


def handle(message: str) -> str:
    action, params = parse(message)

    if action == "confirm_required":
        return (
            "⚠️ Security-sensitive action detected. I need explicit confirmation first. "
            "Please restate with CONFIRM in your message."
        )

    if action == "good_night":
        out = run_ha("routine", "good_night")
        return "🌙 Good night routine complete: lights off, doors lock step executed when available, climate set to night mode."

    if action == "temperature":
        out = run_ha("status", "temperature")
        return fmt_temperature(out)

    if action == "front_door":
        out = run_ha("status", "front_door")
        return fmt_front_door(out)

    if action == "devices_on":
        out = run_ha("status", "on")
        return fmt_devices_on(out)

    if action == "light_off":
        run_ha("light", "off", params["target"])
        return f"💡 Done, turned off `{params['target']}`."

    if action == "light_on":
        run_ha("light", "on", params["target"])
        return f"💡 Done, turned on `{params['target']}`."

    if action == "light_set":
        run_ha("light", "set", params["target"], "--brightness", str(params["brightness"]))
        return f"💡 Done, set `{params['target']}` to {params['brightness']}%."

    return (
        "I can do: turn on/off lights, set lights to %, check temperature, good night, front door status, devices on. "
        "Example: `Turn off the living room lights`"
    )


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: discord_home_command.py '<message>'")
        return 2
    msg = " ".join(sys.argv[1:])
    try:
        print(handle(msg))
        return 0
    except Exception as e:
        print(f"Home command error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
