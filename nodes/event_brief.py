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


def _strip_code_fence(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def _extract_first_json_object(s: str) -> str:
    s = (s or "").strip()
    start = s.find("{")
    if start == -1:
        return s
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
    return s[start:]


def _make_client(base_url: Optional[str] = None, api_key: Optional[str] = None) -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY") 
    base_url = os.getenv("OPENAI_BASE_URL") 
    return OpenAI(api_key=api_key, base_url=base_url)


def event_brief(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 4: Third-party LLM generates event briefs + impact analysis for judge-selected topics.

    Input:
      - state["judge_results"]
      - state["compact_articles"] preferred (for urls/titles)
      - optional: state["event_model"]

    Output:
      - {"event_briefs": [...]}
    """
    judge_results: List[Dict[str, Any]] = state.get("judge_results", []) or []
    if not judge_results:
        return {"event_briefs": []}

    compact_articles: List[Dict[str, Any]] = state.get("compact_articles", []) or []
    event_model = state.get("event_model", "gpt-5-nano")
    temperature = float(state.get("event_temperature", 0.2))


    briefs_input = []
    for jr in judge_results[:8]:
        ids = jr.get("article_ids", []) or []
        ev = []
        for i in ids[:3]:
            if 0 <= i < len(compact_articles):
                a = compact_articles[i]
                ev.append({
                    "title": (a.get("title") or "")[:160],
                    "url": a.get("url") or "",
                    "summary": (a.get("summary") or a.get("raw_summary") or "")[:160],
                })
        briefs_input.append({
            "rank": jr.get("rank"),
            "topic_id": jr.get("topic_id"),
            "topic_label": jr.get("topic_label", ""),
            "final_score": jr.get("final_score"),
            "evidence": ev,
        })

    system = "You are an analyst writing concise event briefs. Return JSON only."
    user = (
        "For each item, write an event brief + impact analysis.\n"
        "Return JSON exactly:\n"
        "{\"event_briefs\":[{\"rank\":1,\"topic_id\":\"T1\",\"headline\":\"...\","
        "\"what_happened\":\"...\",\"why_it_matters\":\"...\",\"market_impact\":\"...\","
        "\"watch_next\":\"...\",\"sources\":[\"url1\",\"url2\"]}]}\n"
        "Keep each field concise (1-3 sentences). Do not invent facts beyond evidence.\n"
        "Input:\n" + json.dumps(briefs_input, ensure_ascii=False, separators=(",", ":"))
    )

    client = _make_client()
    resp = client.chat.completions.create(
        model=event_model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=temperature,
    )

    content = _extract_first_json_object(_strip_code_fence(_extract_content(resp)))
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"[event_brief] Model did not return valid JSON.\nRaw:\n{content[:1500]}") from e

    briefs = parsed.get("event_briefs", [])
    if not isinstance(briefs, list):
        raise RuntimeError("[event_brief] Invalid JSON schema: event_briefs is not a list.")

    print(f"[event_brief] event_briefs={len(briefs)}")
    return {"event_briefs": briefs}
