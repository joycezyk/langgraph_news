
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
    """
    Build an OpenAI-compatible client. SDK requires a non-empty api_key even for proxies.
    """
    api_key =  os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    return OpenAI(api_key=api_key, base_url=base_url)


def _topic_to_evidence(
    topic: Dict[str, Any],
    articles_fallback: List[Dict[str, Any]],
    compact_articles_preferred: Optional[List[Dict[str, Any]]] = None,
    k: int = 3
) -> Dict[str, Any]:
    """
    Build minimal evidence for a topic to save tokens.

    Priority mapping:
    1) compact_articles_preferred (state["compact_articles"])  ✅ accurate mapping
    2) articles_fallback (state["articles"])                   best-effort

    Output schema:
    {
      "topic_id": "...",
      "topic_label": "...",
      "topic_summary": "...",
      "evidence": [{"i":0,"title":"...","url":"..."}]
    }
    """
    ids = topic.get("article_ids", []) or []

    src_list = compact_articles_preferred if isinstance(compact_articles_preferred, list) and compact_articles_preferred else articles_fallback

    picks: List[Dict[str, Any]] = []
    for i in ids[:k]:
        if 0 <= i < len(src_list):
            a = src_list[i]
            picks.append({
                "i": i,
                "title": (a.get("title") or "")[:160],
                "url": a.get("url") or "",
    
                "source": (a.get("source") or "")[:60] if isinstance(a.get("source"), str) else "",
            })

    return {
        "topic_id": topic.get("topic_id", ""),
        "topic_label": topic.get("topic_label", ""),
        "topic_summary": (topic.get("topic_summary") or "")[:240],
        "evidence": picks,
    }


def _score_with_model(
    client: OpenAI,
    model: str,
    evidence: Dict[str, Any],
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """
    Score a topic: 0-10 + short rationale.
    MUST return JSON.
    """
    system = "You are a strict news editor. Return JSON only."
    user = (
        "Score the topic importance for a daily finance/economy briefing.\n"
        "Return JSON exactly: {\"score\": <0-10>, \"rationale\": \"...\"}\n"
        "Scoring guide: 9-10 major market/policy impact; 6-8 meaningful; 3-5 minor; 0-2 noise.\n"
        "Topic:\n"
        + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    content = _extract_content(resp).strip()

    try:
        obj = json.loads(content)
    except json.JSONDecodeError:
        obj = {"score": None, "rationale": content[:600]}


    score = obj.get("score")
    if isinstance(score, str):

        try:
            score = float(score.split("/")[0].strip())
        except Exception:
            score = None

    return {"score": score, "rationale": (obj.get("rationale") or "")[:600]}


def panel_score(state: Dict[str, Any]) -> Dict[str, Any]:

    topics: List[Dict[str, Any]] = state.get("topics", []) or []
    if not topics:
        return {"panel_reviews": []}

    # pick source list for accurate mapping
    compact_articles = state.get("compact_articles")
    articles_fallback: List[Dict[str, Any]] = state.get("articles", []) or []

    top_n = int(state.get("top_topics_for_panel", 8))
    evidence_k = int(state.get("evidence_k", 3))
    topics = topics[:top_n]

    panel_models: List[str] = state.get("panel_models") or [
        "gpt-4o-mini",
        "gpt-4.1-mini",
        "gpt-5-mini",
    ]

    panel_base_urls = state.get("panel_base_urls") 
    panel_api_keys = state.get("panel_api_keys")    
    panel_temp = float(state.get("panel_temperature", 0.2))

    reviews: List[Dict[str, Any]] = []

    for t in topics:
        evidence = _topic_to_evidence(
            topic=t,
            articles_fallback=articles_fallback,
            compact_articles_preferred=compact_articles if isinstance(compact_articles, list) else None,
            k=evidence_k,
        )

        model_outputs: List[Dict[str, Any]] = []
        for idx, m in enumerate(panel_models):
            base_url = None
            api_key = None
            if isinstance(panel_base_urls, list) and idx < len(panel_base_urls):
                base_url = panel_base_urls[idx]
            if isinstance(panel_api_keys, list) and idx < len(panel_api_keys):
                api_key = panel_api_keys[idx]

            client = _make_client(base_url=base_url, api_key=api_key)
            out = _score_with_model(client=client, model=m, evidence=evidence, temperature=panel_temp)

            model_outputs.append({
                "model": m,
                "score": out["score"],
                "rationale": out["rationale"],
            })

        reviews.append({
            "topic_id": t.get("topic_id"),
            "topic_label": t.get("topic_label"),
            "topic_summary": t.get("topic_summary"),
            "article_ids": t.get("article_ids", []),
            "evidence": evidence.get("evidence", []),
            "panel": model_outputs,
        })

    print(f"[panel_score] topics_scored={len(reviews)} panel_models={len(panel_models)}")
    return {"panel_reviews": reviews}