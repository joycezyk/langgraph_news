from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, START, END

from utils.time_window import get_noon_window_utc
from nodes.fetch_news import fetch_news


#define state
class State(TypedDict, total=False):
    since_ts: str
    until_ts: str
    articles: List[Dict[str, Any]]


#set time zone for toronto time from previous day noon to current day noon
def set_time_window(state: State) -> State:
    since_ts, until_ts = get_noon_window_utc()
    return {
        "since_ts": since_ts,
        "until_ts": until_ts
    }


# build langgaraph
graph = (
    StateGraph(State)
    .add_node("set_time_window", set_time_window)
    .add_node("fetch_news", fetch_news)
    .add_edge(START, "set_time_window")
    .add_edge("set_time_window", "fetch_news")
    .add_edge("fetch_news", END)
    .compile()
)


# ===== 程序入口 =====
if __name__ == "__main__":
    result = graph.invoke({})

    articles = result.get("articles", [])
    print("\n===== RUN RESULT =====")
    print(f"Total articles fetched: {len(articles)}\n")

    for i, a in enumerate(articles[:5], 1):
        print(f"{i}. {a['title']}")
        print(f"   Source: {a['source']}")
        print(f"   Time:   {a['published_at']}")
        print(f"   URL:    {a['url']}\n")
