#!/usr/bin/env python3
import os
import json
import textwrap
from datetime import datetime, timezone

import requests


OPENAI_URL = "https://api.openai.com/v1/responses"
BSKY_PDS = "https://bsky.social"
CREATE_SESSION = f"{BSKY_PDS}/xrpc/com.atproto.server.createSession"
CREATE_RECORD = f"{BSKY_PDS}/xrpc/com.atproto.repo.createRecord"


def require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise SystemExit(f"Missing required env var: {name}")
    return v


def openai_generate_post(api_key: str, model: str) -> str:
    # You asked: include "#tank" at the start so it's clearly not "you"
    # We'll force it and also forbid other hashtags/emojis/links.
    prompt = textwrap.dedent(
        """
        Write ONE Bluesky post as a neutral, analytic global outlook snapshot.
        Hard rules:
        - Must start with exactly: "#tank " (including the space).
        - Do not use any other hashtags besides #tank.
        - No emojis.
        - No links/URLs.
        - No first-person voice ("I", "me", "my").
        - Tone: calm, decision-oriented, non-alarmist.
        - Content: global risk posture, major theatres, and whether narrative intensity matches verified action.
        - Length: 240–300 characters if possible. Absolute max: 300 characters.
        Output ONLY the post text.
        """
    ).strip()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "input": prompt,
    }

   r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)

   # If OpenAI returns a 400, print the body so we can see the real reason in Actions logs.
   if r.status_code >= 400:
      print("OpenAI error status:", r.status_code)
      print("OpenAI error body:", r.text)
      r.raise_for_status()

   data = r.json()

    # Responses API output parsing:
    # We search for the first text content chunk.
    text = None
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text") and content.get("text"):
                text = content["text"]
                break
        if text:
            break

    if not text:
        raise RuntimeError("OpenAI response did not include output text in expected format.")

    text = text.strip()

    # Enforce "#tank " prefix no matter what.
    if not text.startswith("#tank "):
        # If it started with "#tank" but missing space, fix it.
        if text.startswith("#tank"):
            text = "#tank " + text[len("#tank"):].lstrip()
        else:
            text = "#tank " + text

    # Enforce max length 300 chars (Bluesky limit is larger, but your requirement is 300).
    if len(text) > 300:
        text = text[:297].rstrip() + "..."

    # Safety: ensure no extra hashtags, emojis, or URLs slipped in.
    lowered = text.lower()
    if "http://" in lowered or "https://" in lowered or "www." in lowered:
        raise RuntimeError("Generated text included a URL. Refusing to post.")

    # Allow only "#tank" as hashtag.
    hashtags = [w for w in text.split() if w.startswith("#")]
    if any(h.lower() != "#tank" for h in hashtags):
        raise RuntimeError(f"Generated text included extra hashtag(s): {hashtags}. Refusing to post.")

    # Basic emoji check (not perfect, but catches common emoji ranges)
    for ch in text:
        if ord(ch) >= 0x1F300 and ord(ch) <= 0x1FAFF:
            raise RuntimeError("Generated text included emoji. Refusing to post.")

    # No first-person
    forbidden = (" i ", " me ", " my ", " i'm", " ive ", " i've ")
    padded = f" {text.lower()} "
    if any(tok in padded for tok in forbidden):
        raise RuntimeError("Generated text used first-person voice. Refusing to post.")

    return text


def bluesky_create_session(handle: str, app_password: str) -> dict:
    payload = {"identifier": handle, "password": app_password}
    r = requests.post(CREATE_SESSION, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def bluesky_create_post(access_jwt: str, repo_did: str, text: str) -> dict:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": now,
    }

    payload = {
        "repo": repo_did,
        "collection": "app.bsky.feed.post",
        "record": record,
    }

    headers = {"Authorization": f"Bearer {access_jwt}"}
    r = requests.post(CREATE_RECORD, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    handle = require_env("BLUESKY_HANDLE")
    app_pw = require_env("BLUESKY_APP_PASSWORD")
    openai_key = require_env("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL") or "gpt-5.2"

    post_text = openai_generate_post(openai_key, model)
    session = bluesky_create_session(handle, app_pw)

    access_jwt = session["accessJwt"]
    repo_did = session["did"]

    res = bluesky_create_post(access_jwt, repo_did, post_text)
    print(f"Posted: {res.get('uri', '(no uri)')}")


if __name__ == "__main__":
    main()
