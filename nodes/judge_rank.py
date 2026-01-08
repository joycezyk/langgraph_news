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


def judge_rank(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 3: Judge LLM aggregates panel_reviews -> judge_results

    Input:
      - state["panel_reviews"]: list
      - optional: state["judge_model"], state["judge_top_k"]

    Output:
      - {"judge_results": [...]}  # sorted, includes final_score, reason
    """
    panel_reviews: List[Dict[str, Any]] = state.get("panel_reviews", []) or []
    if not panel_reviews:
        return {"judge_results": []}

    judge_top_k = int(state.get("judge_top_k", 6))
    judge_model = state.get("judge_model", "gpt-4.1-nano")
    temperature = float(state.get("judge_temperature", 0.2))

    compact = []
    for r in panel_reviews[:12]:
        compact.append({
            "topic_id": r.get("topic_id"),
            "topic_label": r.get("topic_label"),
            "topic_summary": (r.get("topic_summary") or "")[:220],
            "article_ids": r.get("article_ids", []),
            "panel": [
                {
                    "model": p.get("model"),
                    "score": p.get("score"),
                    "rationale": (p.get("rationale") or "")[:200],
                }
                for p in (r.get("panel") or [])
            ],
            "evidence": r.get("evidence", [])[:3],  
        })

    system = "You are a chief editor. Return JSON only."
    user = (
        "Aggregate panel opinions and pick the most important topics for a daily finance/economy briefing.\n"
        "Return JSON exactly:\n"
        "{\"judge_results\":[{\"rank\":1,\"topic_id\":\"T1\",\"final_score\":9.2,"
        "\"decision_reason\":\"...\",\"article_ids\":[0],\"top_urls\":[\"...\"]}]}\n"
        f"Rules: final_score is 0-10. Select top {judge_top_k}. Keep reasons concise.\n"
        "Input:\n" + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    )

    client = _make_client()
    resp = client.chat.completions.create(
        model=judge_model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=temperature,
    )

    content = _extract_first_json_object(_strip_code_fence(_extract_content(resp)))

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"[judge_rank] Model did not return valid JSON.\nRaw:\n{content[:1500]}") from e

    results = parsed.get("judge_results", [])
    if not isinstance(results, list):
        raise RuntimeError("[judge_rank] Invalid JSON schema: judge_results is not a list.")


    def _score(x):
        s = x.get("final_score")
        try:
            return float(s)
        except Exception:
            return -1.0

    results = sorted(results, key=_score, reverse=True)[:judge_top_k]
    for i, it in enumerate(results, start=1):
        it["rank"] = i

    print(f"[judge_rank] judge_results={len(results)}")
    return {"judge_results": results}
