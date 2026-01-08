import os
import json
from typing import Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI


ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")  


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
        # 去掉开头 ```json 或 ```
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        # 去掉结尾 ```
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



def _build_compact_articles(
    articles: List[Dict[str, Any]],
    max_articles: int,
    max_summary_chars: int,
) -> List[Dict[str, Any]]:

    compact: List[Dict[str, Any]] = []
    for idx, a in enumerate(articles[:max_articles]):
        compact.append({
            "id": idx,
            "title": (a.get("title") or "")[:120],  # ✅ 修复切片
            "summary": (a.get("raw_summary") or a.get("summary") or "")[:max_summary_chars],
            "url": a.get("url", ""),
        })
    return compact


def _shrink_for_free_limit(
    articles: List[Dict[str, Any]],
    max_articles: int,
    max_summary_chars: int,
) -> List[Dict[str, Any]]:

    MAX_CHARS = 15000

    a_n = max_articles
    s_n = max_summary_chars

    while True:
        compact = _build_compact_articles(articles, a_n, s_n)
        payload = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        if len(payload) <= MAX_CHARS:
            return compact


        if a_n > 4:
            a_n -= 1
            continue
        if s_n > 40:
            s_n -= 10
            continue


        return compact


def cluster_topics(state: Dict[str, Any]) -> Dict[str, Any]:
    articles = state.get("articles", []) or []
    if not articles:
        return {"topics": []}


    model = state.get("model", "gpt-4o-mini")
    temperature = float(state.get("temperature", 0.2))


    max_articles = int(state.get("max_articles", 100))
    max_summary_chars = int(state.get("max_summary_chars", 80))


    api_key = OPENAI_API_KEY or "sk-anything"
    base_url = OPENAI_BASE_URL or "https://api.chatanywhere.tech/v1"
    client = OpenAI(api_key=api_key, base_url=base_url)


    compact_articles = _shrink_for_free_limit(
        articles=articles,
        max_articles=max_articles,
        max_summary_chars=max_summary_chars,
    )

    system_prompt = "Group articles into topic categories. Return JSON only."


    user_prompt = (
        "Return JSON exactly like:\n"
        "{\"topics\":[{\"topic_id\":\"T1\",\"topic_label\":\"...\",\"topic_summary\":\"...\",\"article_ids\":[0]}]}\n"
        "Rules: Each article must belong to exactly one topic.\n"
        "Articles:\n"
        + json.dumps(compact_articles, ensure_ascii=False, separators=(",", ":"))
    )


    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )

    content = _extract_content(resp)


    content = _strip_code_fence(content)
    content = _extract_first_json_object(content)

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"[cluster_topics] Model did not return valid JSON.\nRaw:\n{content[:1500]}") from e


    topics = parsed.get("topics", [])
    if not isinstance(topics, list):
        raise RuntimeError(f"[cluster_topics] Invalid schema: 'topics' is not a list.\nRaw:\n{content[:1500]}")

    print(
        f"[cluster_topics] input_articles={len(articles)} "
        f"sent={len(compact_articles)} topics={len(topics)}"
    )
    return {"topics": topics, "compact_articles": compact_articles}

