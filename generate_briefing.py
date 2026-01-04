import os
from datetime import datetime, timezone
import email.utils
from openai import OpenAI

FEED_PATH = "briefing.xml"
SITE_LINK = "https://newghostisfun.github.io/daily-briefing/"

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def rfc822_now_gmt() -> str:
    now = datetime.now(timezone.utc)
    return email.utils.format_datetime(now)

def ymd_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def build_xml(title: str, briefing_text: str, pubdate: str, guid: str) -> str:
    # Alexa Flash Briefing parser is picky: keep CDATA inline and ASCII-safe.
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Morning Briefing</title>
    <link>{SITE_LINK}</link>
    <description>Private daily briefing</description>
    <language>en-gb</language>

    <item>
      <title>{title}</title>
      <description><![CDATA[{briefing_text}]]></description>
      <pubDate>{pubdate}</pubDate>
      <guid isPermaLink="false">{guid}</guid>
    </item>

  </channel>
</rss>
"""

def main():
    # Keep this "voice-first" and consistent.
    prompt = """Write a calm, analyst-style morning briefing for Alexa.

Hard constraints:
- 2–3 minutes spoken max.
- Short sentences. Clear section headers.
- No URLs. No emojis. Plain punctuation.

Structure:
1) What changed since yesterday (high signal only)
2) Venezuela update
3) UK response signals
4) Legal/docket watch (Epstein-related): if none, say none
5) What to watch today (2–4 concrete signals)

Tone: calm analyst. No hype. No speculation beyond "watch for X".
End with: "End of briefing."
"""

    # Use a small, fast model; you can swap to gpt-4.1-mini etc later.
    resp = client.responses.create(
        model="gpt-4o-mini",
        input=prompt,
    )
    briefing_text = resp.output_text.strip()

    # Extra safety: avoid smart quotes if they appear.
    briefing_text = (
        briefing_text.replace("“", '"').replace("”", '"')
        .replace("‘", "'").replace("’", "'")
        .replace("—", "-").replace("…", "...")
    )

    pubdate = rfc822_now_gmt()
    ymd = ymd_utc()
    title = f"Daily Briefing - {ymd}"
    guid = f"mj-briefing-{ymd}"

    xml = build_xml(title, briefing_text, pubdate, guid)

    with open(FEED_PATH, "w", encoding="utf-8") as f:
        f.write(xml)

if __name__ == "__main__":
    main()
