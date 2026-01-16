#!/usr/bin/env python3

import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

OPENAI_URL = "https://api.openai.com/v1/responses"
BSKY_PDS = "https://bsky.social"
CREATE_SESSION = f"{BSKY_PDS}/xrpc/com.atproto.server.createSession"
CREATE_RECORD = f"{BSKY_PDS}/xrpc/com.atproto.repo.createRecord"

SIGNAL_PATH = Path("signals/high_profile.json")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def utc_today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_high_profile_signal():
    """
    Returns (flagged: bool, summary: str|None)
    Only returns flagged=True if:
      - file exists
      - date_utc == today (UTC)
      - flag == true
    """
    if not SIGNAL_PATH.exists():
        return (False, None)

    try:
        data = json.loads(SIGNAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return (False, None)

    if data.get("date_utc") != utc_today_str():
        return (False, None)

    if bool(data.get("flag")) is not True:
        return (False, None)

    summary = data.get("summary")
    if isinstance(summary, str):
        summary = summary.strip()
    else:
        summary = None

    return (True, summary)


def openai_generate_post(api_key: str, model: str, flagged: bool, flag_summary: str | None) -> str:
    if flagged:
        # SPECIAL mode: short, factual, “cut-through” tone; still your sceptical voice.
        # Still must start "#tank " but we add "SPECIAL:" immediately after.
        base = "SPECIAL: "
        summary_hint = f" High-profile signal: {flag_summary} " if flag_summary else ""
        prompt = f"""
Write ONE Bluesky post in a crisp, plain style.

Hard rules:
- Must start with exactly: "#tank " (including the space), then immediately "{base}"
- No other hashtags. No emojis. No links. No first-person.
- Target length: 160–200 characters. Hard max 200.
- Style: factual, no waffle, no list of regions.
- Say what happened (high-profile), and what it changes to watch today.
- Avoid filler words like: "posture", "heightened", "reflects", "such as", "complex".

Context:{summary_hint}

Output ONLY the post text.
""".strip()
    else:
        # Normal locked voice (your approved style)
        prompt = """
Write ONE Bluesky post in a crisp, plain style.

Hard rules:
- Must start with exactly: "#tank " (including the space).
- No other hashtags. No emojis. No links. No first-person.
- Target length: 160–200 characters. Hard max 200.
- Voice: sceptical, grounded, mildly admonishing.
- Must convey: global risk still high; driven more by baseless words than action; leaders need to lead not soundbite; decisions and consequences lag behind noise.
- Do NOT name specific regions or theatres.

Output ONLY the post text.
""".strip()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "input": prompt,
        "max_output_tokens": 80,
    }

    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
    if r.status_code >= 400:
        print("OpenAI error:", r.status_code, r.text)
        r.raise_for_status()

    data = r.json()

    text = None
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text") and content.get("text"):
                text = content["text"]
                break
        if text:
            break

    if not text:
        raise RuntimeError("No text returned from OpenAI")

    text = text.strip()

    # Enforce #tank prefix
    if not text.startswith("#tank "):
        if text.startswith("#tank"):
            text = "#tank " + text[len("#tank"):].lstrip()
        else:
            text = "#tank " + text

    # Enforce SPECIAL label if flagged
    if flagged and not text.startswith("#tank SPECIAL:"):
        # Keep the required "#tank " start; insert SPECIAL:
        if text.startswith("#tank "):
            rest = text[len("#tank "):].lstrip()
            text = "#tank SPECIAL: " + rest

    # Enforce length cap 200
    if len(text) > 200:
        text = text[:197].rstrip() + "..."

    # Safety checks
    lowered = text.lower()
    if "http://" in lowered or "https://" in lowered or "www." in lowered:
        raise RuntimeError("Post contains URL")

    hashtags = [w for w in text.split() if w.startswith("#")]
    if any(h.lower() != "#tank" for h in hashtags):
        raise RuntimeError("Extra hashtag detected")

    # Emoji range check (basic)
    for ch in text:
        if 0x1F300 <= ord(ch) <= 0x1FAFF:
            raise RuntimeError("Emoji detected")

    padded = f" {lowered} "
    for bad in (" i ", " me ", " my ", " i'm", " ive ", " i've "):
        if bad in padded:
            raise RuntimeError("First-person voice detected")

    return text


def bluesky_create_session(handle: str, app_password: str) -> dict:
    r = requests.post(
        CREATE_SESSION,
        json={"identifier": handle, "password": app_password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def bluesky_create_post(access_jwt: str, repo_did: str, text: str) -> dict:
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    r = requests.post(
        CREATE_RECORD,
        headers={"Authorization": f"Bearer {access_jwt}"},
        json={
            "repo": repo_did,
            "collection": "app.bsky.feed.post",
            "record": record,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def main():
    handle = require_env("BLUESKY_HANDLE")
    app_pw = require_env("BLUESKY_APP_PASSWORD")
    openai_key = require_env("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

    flagged, summary = load_high_profile_signal()
    print("Posting as:", handle)
    print("High-profile flagged:", flagged)
    if summary:
        print("Flag summary:", summary)

    post_text = openai_generate_post(openai_key, model, flagged, summary)
    print("Generated post:", post_text)

    session = bluesky_create_session(handle, app_pw)
    result = bluesky_create_post(session["accessJwt"], session["did"], post_text)
    print("POSTED:", result.get("uri"))


if __name__ == "__main__":
    main()
