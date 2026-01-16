def openai_generate_post(api_key: str, model: str) -> str:
    prompt = """
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
        print("OpenAI error status:", r.status_code)
        print("OpenAI error body:", r.text)
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
        raise RuntimeError("OpenAI response did not include output text.")

    text = text.strip()

    if not text.startswith("#tank "):
        if text.startswith("#tank"):
            text = "#tank " + text[len("#tank"):].lstrip()
        else:
            text = "#tank " + text

    if len(text) > 300:
        text = text[:297].rstrip() + "..."

    lowered = text.lower()
    if "http://" in lowered or "https://" in lowered or "www." in lowered:
        raise RuntimeError("Generated text included a URL.")

    hashtags = [w for w in text.split() if w.startswith("#")]
    if any(h.lower() != "#tank" for h in hashtags):
        raise RuntimeError("Generated text included extra hashtags.")

    for ch in text:
        if 0x1F300 <= ord(ch) <= 0x1FAFF:
            raise RuntimeError("Generated text included emoji.")

    padded = f" {text.lower()} "
    for bad in (" i ", " me ", " my ", " i'm", " ive ", " i've "):
        if bad in padded:
            raise RuntimeError("Generated text used first-person voice.")

    return text
def main():
    handle = require_env("BLUESKY_HANDLE")
    app_pw = require_env("BLUESKY_APP_PASSWORD")
    openai_key = require_env("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL") or "gpt-5.2"

    print("Handle:", handle)

    post_text = openai_generate_post(openai_key, model)
    print("Generated post:", post_text)

    session = bluesky_create_session(handle, app_pw)
    print("Session DID:", session["did"])

    access_jwt = session["accessJwt"]
    repo_did = session["did"]

    res = bluesky_create_post(access_jwt, repo_did, post_text)
    print("POST RESULT:", res)


if __name__ == "__main__":
    main()

