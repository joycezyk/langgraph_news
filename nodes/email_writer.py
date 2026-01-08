import os
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)


def _extract_content(resp) -> str:
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        if "choices" in resp:
            return resp["choices"][0]["message"]["content"]
        if "content" in resp:
            return resp["content"]
        return json.dumps(resp, ensure_ascii=False)
    return resp.choices[0].message.content


def _make_client(base_url: Optional[str] = None, api_key: Optional[str] = None) -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    return OpenAI(api_key=api_key, base_url=base_url)


def email_writer(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 5: GPT writes the final email using event_briefs (and optionally judge_results).

    Input:
      - state["event_briefs"] (preferred)
      - optional: state["email_model"], state["audience"], state["email_subject"]

    Output:
      - {"email_text": "..."}
    """
    briefs: List[Dict[str, Any]] = state.get("event_briefs", []) or []
    if not briefs:
        return {"email_text": "No event briefs available."}

    email_model = state.get("email_model", "gpt-3.5-turbo")
    temperature = float(state.get("email_temperature", 0.3))
    audience = state.get("audience", "Busy finance professional")
    subject = state.get("email_subject", "Daily Markets & Macro Briefing")

    payload = []
    for b in briefs[:8]:
        payload.append({
            "rank": b.get("rank"),
            "headline": b.get("headline"),
            "what_happened": b.get("what_happened"),
            "why_it_matters": b.get("why_it_matters"),
            "market_impact": b.get("market_impact"),
            "watch_next": b.get("watch_next"),
            "sources": (b.get("sources") or [])[:2],
        })

    system = "You write clear, scannable emails. Keep it concise and professional."
    user = (
        f"Write an email briefing for: {audience}\n"
        f"Subject line: {subject}\n"
        "Format:\n"
        "- Subject: ...\n"
        "- Then a short intro (1-2 lines)\n"
        "- Then numbered items (1..N), each with: Headline + 3 bullets (what/why/impact) + Sources\n"
        "- Then a short 'Watch Next' section\n"
        "Use the provided briefs only; do not invent facts.\n\n"
        "Briefs:\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )

    client = _make_client()
    resp = client.chat.completions.create(
        model=email_model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=temperature,
    )

    email_text = _extract_content(resp).strip()
    return {"email_text": email_text}
