import os
import json
from typing import List, Dict, Any
from openai import OpenAI


def extract_content(resp) -> str:
    """
    兼容：第三方 proxy 可能返回 str / dict / 官方 SDK 对象
    """
    if isinstance(resp, str):
        return resp

    if isinstance(resp, dict):
        # 常见 OpenAI-compatible dict
        if "choices" in resp:
            return resp["choices"][0]["message"]["content"]
        # 有些代理直接返回 {"content": "..."}
        if "content" in resp:
            return resp["content"]
        # 兜底：方便 debug
        return json.dumps(resp, ensure_ascii=False)

    # 官方 OpenAI SDK 对象
    return resp.choices[0].message.content


def cluster_articles_into_topics(
    articles: List[Dict[str, Any]],
    model: str = "gpt-4o-mini"
) -> List[Dict[str, Any]]:
    """
    Use GPT to cluster news articles into TOPIC-based groups.
    OpenAI-compatible (proxy-friendly).
    """

    # ✅ 推荐：用环境变量；没设置就用兜底，避免 api_key=None 报错
    # 在终端可设置：
    # export OPENAI_API_KEY="sk-xxx"
    # export OPENAI_BASE_URL="https://api.chatanywhere.tech/v1"
    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY", "sk-VNWcLkfdtfjRaqAY25bY6YHcvZGeQnyrgJrElOYmQvvmAPQR"),
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.chatanywhere.tech/v1"),
    )

    # ✅ 压缩字段，省 token
    compact_articles = []
    for idx, a in enumerate(articles):
        compact_articles.append({
            "id": idx,
            "title": a.get("title", ""),
            "source": a.get("source", ""),
            "published_at": a.get("published_at", ""),
            "summary": (a.get("raw_summary") or "")[:300],
        })

    system_prompt = (
        "You are a news taxonomy assistant.\n"
        "Your task is to group news articles into TOPIC categories.\n\n"
        "Rules:\n"
        "- Topics are thematic categories (e.g. 'US Interest Rates', 'Crypto Markets'), not single events.\n"
        "- Every article must belong to exactly ONE topic.\n"
        "- Topics should be concise and reusable.\n"
        "- Do NOT invent facts.\n"
        "- Output MUST be valid JSON only.\n"
    )

    user_prompt = f"""
Group the following articles into topic categories.

Return JSON in this exact format:
{{
  "topics": [
    {{
      "topic_id": "T1",
      "topic_label": "Short topic name",
      "topic_summary": "1-2 sentence explanation",
      "article_ids": [0, 2, 5]
    }}
  ]
}}

ARTICLES:
{json.dumps(compact_articles, ensure_ascii=False, indent=2)}
"""

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    content = extract_content(resp)

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"GPT did not return valid JSON. Raw output:\n{content[:1500]}") from e

    return parsed["topics"]


if __name__ == "__main__":
    # 模拟你 fetch_news 得到的 articles
    demo_articles = [
        {
            "title": "Fed officials signal rates may stay higher for longer",
            "source": "Reuters",
            "published_at": "2026-01-06T14:32:00Z",
            "raw_summary": "Several Federal Reserve officials said inflation risks remain elevated.",
            "url": "https://example.com/1",
        },
        {
            "title": "Bitcoin slides as risk appetite fades",
            "source": "Bloomberg",
            "published_at": "2026-01-06T10:20:00Z",
            "raw_summary": "Cryptocurrencies fell amid broader market weakness.",
            "url": "https://example.com/2",
        },
        {
            "title": "US stocks dip ahead of CPI data",
            "source": "CNBC",
            "published_at": "2026-01-06T11:10:00Z",
            "raw_summary": "Investors are cautious before the release of inflation data.",
            "url": "https://example.com/3",
        },
    ]

    print("🚀 Running topic clustering...\n")

    try:
        topics = cluster_articles_into_topics(demo_articles)

        print("===== TOPICS =====")
        for t in topics:
            print(json.dumps(t, indent=2, ensure_ascii=False))

    except Exception as e:
        print("❌ Error occurred:")
        print(e)
