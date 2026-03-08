#!/usr/bin/env python3

import json
import os
import sys
from datetime import datetime, timezone

import requests


OPENAI_URL = "https://api.openai.com/v1/responses"
BSKY_CREATE_SESSION_URL = "https://bsky.social/xrpc/com.atproto.server.createSession"
BSKY_CREATE_RECORD_URL = "https://bsky.social/xrpc/com.atproto.repo.createRecord"


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def openai_generate_post(
    api_key: str,
    model: str,
    flagged: bool = False,
    flag_summary: str | None = None,
) -> str:
    if flagged:
        prompt = f"""
Write ONE Bluesky post in a crisp, plain style.

Hard rules:
- Must start with exactly: "SPECIAL: "
- No emojis.
- No links.
- No first-person.
- Target length: 160–200 characters. Hard max 200.
- Style: plain, sceptical, consequence-focused.
- Say what happened and what to watch next, without hype.
- Output only the post text.

Context:
{flag_summary or "No extra context provided."}
""".strip()
    else:
        prompt = """
Write ONE Bluesky post in a crisp, plain style.

Hard rules:
- Must start with exactly: "#tank " including the space.
- No other hashtags.
- No emojis.
- No links.
- No first-person.
- Target length: 240–300 characters.
- Tone: neutral, analytic.
- Focus on global risk posture and whether narrative matches action.
- Do not name specific regions or theatres.
- Output only the post text.
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

    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()

    text = None
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text"):
                text = content.get("text")
                if text:
                    break
        if text:
            break

    if not text:
        raise RuntimeError(f"No text returned from OpenAI: {json.dumps(data, ensure_ascii=False)}")

    text = text.strip()

    # Enforce prefix
    if flagged:
        if text.startswith("SPECIAL:"):
            text = "SPECIAL: " + text[len("SPECIAL:"):].lstrip()
        else:
            text = "SPECIAL: " + text
    else:
        if text.startswith("#tank "):
            text = "#tank " + text[len("#tank "):].lstrip()
        else:
            text = "#tank " + text

    # Word-safe truncation
    max_len = 200 if flagged else 300
    if len(text) > max_len:
        cut = text[:max_len]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        text = cut.rstrip(" .,;:-") + "…"

    # Safety checks
    lowered = text.lower()

    if "http://" in lowered or "https://" in lowered or "www." in lowered:
        raise RuntimeError("Post contains URL")

    hashtags = [word for word in text.split() if word.startswith("#")]
    if flagged:
        if hashtags:
            raise RuntimeError("Flagged post contains hashtag")
    else:
        if any(tag.lower() != "#tank" for tag in hashtags):
            raise RuntimeError("Extra hashtag detected")

    for ch in text:
        cp = ord(ch)
        if (
            0x1F300 <= cp <= 0x1FAFF
            or 0x2600 <= cp <= 0x27BF
            or 0xFE00 <= cp <= 0xFE0F
        ):
            raise RuntimeError("Emoji detected")

    padded = f" {lowered} "
    for bad in (" i ", " me ", " my ", " mine ", " i'm", " ive ", " i've ", " i'd ", " i'll "):
        if bad in padded:
            raise RuntimeError("First-person voice detected")

    return text


def bluesky_login(handle: str, app_password: str) -> tuple[str, str]:
    payload = {
        "identifier": handle,
        "password": app_password,
    }

    r = requests.post(BSKY_CREATE_SESSION_URL, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()

    access_jwt = data.get("accessJwt")
    did = data.get("did")

    if not access_jwt or not did:
        raise RuntimeError(f"Bluesky login failed: {json.dumps(data, ensure_ascii=False)}")

    return access_jwt, did


def bluesky_create_post(access_jwt: str, did: str, text: str) -> dict:
    headers = {
        "Authorization": f"Bearer {access_jwt}",
        "Content-Type": "application/json",
    }

    payload = {
        "repo": did,
        "collection": "app.bsky.feed.post",
        "record": {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }

    r = requests.post(BSKY_CREATE_RECORD_URL, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> None:
    handle = require_env("BLUESKY_HANDLE")
    app_password = require_env("BLUESKY_APP_PASSWORD")
    openai_api_key = require_env("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"

    flagged_raw = os.getenv("FLAGGED", "false").strip().lower()
    flagged = flagged_raw in {"1", "true", "yes", "y", "on"}
    flag_summary = os.getenv("FLAG_SUMMARY", "").strip() or None

    print("Posting as:", handle)
    print("Flagged mode:", flagged)

    post_text = openai_generate_post(
        api_key=openai_api_key,
        model=openai_model,
        flagged=flagged,
        flag_summary=flag_summary,
    )

    print("Generated post:", repr(post_text))

    access_jwt, did = bluesky_login(handle, app_password)
    result = bluesky_create_post(access_jwt, did, post_text)

    print("Bluesky post created.")
    print("URI:", result.get("uri"))
    print("CID:", result.get("cid"))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
