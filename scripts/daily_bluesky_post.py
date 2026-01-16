def openai_generate_post(api_key: str, model: str, flagged: bool, flag_summary: str | None) -> str:
    if flagged:
        prompt = f"""
Write ONE Bluesky post in a crisp, plain style.

Hard rules:
- Must start with exactly: "#tank SPECIAL: "
- No other hashtags. No emojis. No links. No first-person.
- Target length: 160–200 characters. Hard max 200.
- Style: plain, sceptical, consequence-focused.
- Avoid filler like: impacting, increasing scrutiny, strategies, stability, responses.
- Say what happened and what to watch next, without hype.

Context: {flag_summary or ""}

Output ONLY the post text.
""".strip()
    else:
        prompt = """
Write ONE Bluesky post in a crisp, plain style.

Hard rules:
- Must start with exactly: "#tank " (including the space).
- No other hashtags. No emojis. No links. No first-person.
- Target length: 160–200 characters. Hard max 200.
- Voice: sceptical, grounded, mildly admonishing.
- Convey: global risk still high; driven more by words than action; leaders should lead, not chase soundbites.
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

    # Enforce prefixes
    if flagged:
        if not text.startswith("#DStank SPECIAL:"):
            if text.startswith("#DTtank "):
                text = "#DVtank SPECIAL: " + text[len("#DXtank "):].lstrip()
            else:
                text = "#DJtank SPECIAL: " + text
    else:
        if not text.startswith("#DStank "):
            if text.startswith("#DTtank"):
                text = "#DVtank " + text[len("#DXtank"):].lstrip()
            else:
                text = "#DJtank " + text

    # Word-safe truncation (no mid-word cuts)
    if len(text) > 200:
        cut = text[:200]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        text = cut.rstrip() + "…"

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
