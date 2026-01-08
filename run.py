from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, START, END

from utils.time_window import get_noon_window_utc
from nodes.fetch_news import fetch_news
from nodes.cluster_topics import cluster_topics
from nodes.panel_score import panel_score
from nodes.judge_rank import judge_rank
from nodes.event_brief import event_brief
from nodes.email_writer import email_writer


# define state
class State(TypedDict, total=False):
    since_ts: str
    until_ts: str
    articles: List[Dict[str, Any]]


    topics: List[Dict[str, Any]]
    compact_articles: List[Dict[str, Any]]


    sections: List[Dict[str, Any]]
    panel_reviews: List[Dict[str, Any]]
    judge_results: List[Dict[str, Any]]

    event_briefs: List[Dict[str, Any]]
    email_text: str


# set time zone window: Toronto previous noon -> current noon (UTC timestamps)
def set_time_window(state: State) -> State:
    since_ts, until_ts = get_noon_window_utc()
    return {
        "since_ts": since_ts,
        "until_ts": until_ts
    }


# build langgraph
graph = (
    StateGraph(State)
    .add_node("set_time_window", set_time_window)
    .add_node("fetch_news", fetch_news)
    .add_node("cluster_topics", cluster_topics)   
    .add_node("panel_score", panel_score)
    .add_node("judge_rank", judge_rank)
    .add_node("event_brief", event_brief)
    .add_node("email_writer", email_writer)

    .add_edge(START, "set_time_window")
    .add_edge("set_time_window", "fetch_news")
    .add_edge("fetch_news", "cluster_topics")   
    .add_edge("cluster_topics", "panel_score")
    .add_edge("panel_score", "judge_rank")
    .add_edge("judge_rank", "event_brief")
    .add_edge("event_brief", "email_writer")
    .add_edge("email_writer", END)
    .compile()
)


if __name__ == "__main__":
    result = graph.invoke({})


    print("\n================ STEP 1: FETCH_NEWS ================")
    articles = result.get("articles", [])
    print(f"Fetched articles: {len(articles)}")
    for i, a in enumerate(articles[:5]):
        print(f"[{i}] {a.get('title')} | {a.get('source')}")


    print("\n================ STEP 2: CLUSTER_TOPICS ================")
    topics = result.get("topics", [])
    print(f"Topics found: {len(topics)}\n")
    for t in topics:
        print(f"{t.get('topic_id')} | {t.get('topic_label')}")
        print(f"  Summary: {t.get('topic_summary')}")
        print(f"  Article IDs: {t.get('article_ids')}\n")


    print("\n================ STEP 3: PANEL_SCORE ================")
    panel_reviews = result.get("panel_reviews", [])
    print(f"Topics reviewed by panel: {len(panel_reviews)}\n")

    for r in panel_reviews:
        print(f"[{r.get('topic_id')}] {r.get('topic_label')}")
        print(f"Topic summary: {r.get('topic_summary')}")
        print("Evidence articles:")
        for ev in r.get("evidence", []):
            print(f"  - ({ev.get('i')}) {ev.get('title')} | {ev.get('url')}")
        print("\nPanel evaluations:")
        for p in r.get("panel", []):
            print(
                f"  • Model: {p.get('model')}\n"
                f"    Score: {p.get('score')}\n"
                f"    Rationale: {p.get('rationale')}"
            )
        print("-" * 60)


    print("\n================ STEP 4: JUDGE_RANK ================")
    judge_results = result.get("judge_results", [])
    print(f"Final topics selected by judge: {len(judge_results)}\n")

    for j in judge_results:
        print(
            f"Rank {j.get('rank')} | {j.get('topic_label')} | "
            f"Final Score: {j.get('final_score')}"
        )
        print(f"Decision reason: {j.get('decision_reason')}")
        print(f"Article IDs: {j.get('article_ids')}")
        print(f"Top URLs: {j.get('top_urls')}")
        print("-" * 60)


    print("\n================ STEP 5: EVENT_BRIEF ================")
    event_briefs = result.get("event_briefs", [])
    print(f"Event briefs generated: {len(event_briefs)}\n")

    for b in event_briefs:
        print(f"#{b.get('rank')} {b.get('headline')}")
        print(f"• What happened: {b.get('what_happened')}")
        print(f"• Why it matters: {b.get('why_it_matters')}")
        print(f"• Market impact: {b.get('market_impact')}")
        print(f"• Watch next: {b.get('watch_next')}")
        print("Sources:")
        for s in b.get("sources", []):
            print(f"  - {s}")
        print("-" * 60)


    print("\n================ STEP 6: EMAIL_WRITER ================")
    email_text = result.get("email_text", "")
    print(email_text)
