#!/usr/bin/env python3

import os
import requests
from datetime import datetime, timezone

# --------------------
# Constants
# --------------------
OPENAI_URL = "https://api.openai.com/v1/responses"
BSKY_PDS = "https://bsky.social"
CREATE_SESSION = f"{BSKY_PDS}/xrpc/com.atproto.server.createSession"
CREATE_RECORD = f"{BSKY_PDS}/xrpc/com.atproto.repo.createRecord"

# --------------------
# Helpers
# --------------------
def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

# --------------------
# OpenAI generation
# --------------------
def openai_generate_post(api_key: str, model: str) -> str:
    prompt = """
Write ONE Bluesky post as a neutral, analytic global outlook snapshot.

Rules:
- Must start with exactly: "#tank " (including the space)
- No other hashtags
- No emojis
- No links
- No first-person voice
- Calm, analytic, non-alarmist
- Mention global risk posture and whether narrative matches verified action
- Target length: about 180 characters (acceptable range 160–200). Hard max 200.

Output ONLY the post text.
""".strip()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "input": prompt,
        "max_output_tokens": 120,
    }

    r = requests.post(
        OPENAI_URL,
        headers=headers,
        json=payload,
        timeout=60,
    )

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

    # Enforce length (hard cap 200 chars)
    if len(text) > 200:
        text = text[:197].rstrip() + "..."

    # Safety checks
    lowered = text.lower()
    if "http://" in lowered or "https://" in lowered or "www." in lowered:
        raise RuntimeError("Post contains URL")

    hashtags = [w for w in text.split() if w.startswith("#")]
    if any(h.lower() != "#tank" for h in hashtags):
        raise RuntimeError("Extra hashtag detected")

    for ch in text:
        if 0x1F300 <= ord(ch) <= 0x1FAFF:
            raise RuntimeError("Emoji detected")

    padded = f" {lowered} "
    for bad in (" i ", " me ", " my ", " i'm", " ive ", " i've "):
        if bad in padded:
            raise RuntimeError("First-person voice detected")

    return text

# --------------------
# Bluesky API
# --------------------
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

# --------------------
# Main
# --------------------
def main():
    handle = require_env("BLUESKY_HANDLE")
    app_pw = require_env("BLUESKY_APP_PASSWORD")
    openai_key = require_env("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

    print("Posting as:", handle)

    post_text = openai_generate_post(openai_key, model)
    print("Generated post:", post_text)

    session = bluesky_create_session(handle, app_pw)
    print("Session DID:", session["did"])

    result = bluesky_create_post(
        session["accessJwt"],
        session["did"],
        post_text,
    )

    print("POSTED:", result.get("uri"))

if __name__ == "__main__":
    main()
