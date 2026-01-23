def openai_generate_post(api_key: str, model: str, flagged: bool = False, flag_summary: str | None = None) -> str:
    if flagged:
        prompt = f"""
Write ONE Bluesky post in a crisp, plain style.

Hard rules:
- Must start with exactly: "SPECIAL: "
- No emojis. No links. No first-person.
- Target length: 160–200 characters. Hard max 200.
- Style: plain, sceptical, consequence-focused.

Context: {flag_summary or ""}

Output ONLY the post text.
""".strip()
    else:
        prompt = """
Write ONE Bluesky post in a crisp, plain style.

Hard rules:
- No emojis. No links. No first-person.
- Target length: 240–300 characters.
- Tone: neutral, analytic.
- Focus on global risk posture and whether narrative matches action.

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

    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
    if r.status_code >= 400:
        print("OpenAI error:", r.status_code, r.text)
        r.raise_for_status()

    data = r.json()

    text = None
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text"):
                text = content.get("text")
                break
        if text:
            break

    if not text:
        raise RuntimeError("No text returned from OpenAI")

    text = text.strip()

    # Final hard cap safety
    if len(text) > 300:
        text = text[:297].rstrip() + "..."

    return text
