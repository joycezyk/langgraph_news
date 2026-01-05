import os
import hashlib
from typing import Dict, Any, List
import requests
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

import os
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
NEWS_ENDPOINT = "https://newsapi.org/v2/everything"

def _hash_url(u: str) -> str:
    return hashlib.sha256(u.encode("utf-8")).hexdigest()[:16]

def fetch_news(state: Dict[str, Any]) -> Dict[str, Any]:
    if not NEWSAPI_KEY:
        raise RuntimeError("Missing NEWSAPI_KEY. Put it in .env as NEWSAPI_KEY=...")

    since = state.get("since_ts")
    until = state.get("until_ts")
    if not since or not until:
        raise ValueError("state must contain 'since_ts' and 'until_ts' (ISO strings).")

    query = state.get("query") or "finance OR economy OR markets OR stocks OR crypto"
    domains = state.get("domains")  # optional
    language = state.get("language") or "en"

    base_params = {
        "q": query,
        "language": language,
        "from": since,
        "to": until,
        "sortBy": "publishedAt",
        "pageSize": 100,
        "apiKey": NEWSAPI_KEY,
    }
    if domains:
        base_params["domains"] = domains

    all_articles: List[Dict[str, Any]] = []

    for page in range(1, 6):
        params = dict(base_params)
        params["page"] = page

        # ✅ 关键：这里用 NEWS_ENDPOINT，不用 url 变量名
        resp = requests.get(NEWS_ENDPOINT, params=params, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"NewsAPI error {resp.status_code}: {resp.text}")

        articles = resp.json().get("articles", [])

        for a in articles:
            link = a.get("url", "")  # ✅ 关键：这里别叫 url，避免和 endpoint 混
            if not link:
                continue
            all_articles.append({
                "published_at": a.get("publishedAt"),
                "source": (a.get("source") or {}).get("name"),
                "title": a.get("title"),
                "url": link,
                "raw_summary": a.get("description") or "",
                "url_hash": _hash_url(link),
            })

        if len(articles) < base_params["pageSize"]:
            break

    # 去重
    seen = set()
    deduped = []
    for item in all_articles:
        h = item["url_hash"]
        if h in seen:
            continue
        seen.add(h)
        deduped.append(item)

    print(f"[fetch_news] window={since} -> {until}, fetched={len(all_articles)}, deduped={len(deduped)}")
    return {"articles": deduped}
