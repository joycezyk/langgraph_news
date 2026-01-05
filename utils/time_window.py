from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo

TORONTO = ZoneInfo("America/Toronto")

def get_noon_window_utc(now_local: datetime | None = None):
    if now_local is None:
        now_local = datetime.now(TORONTO)

    today_noon = datetime.combine(
        now_local.date(),
        time(12, 0),
        tzinfo=TORONTO
    )

    yesterday_noon = today_noon - timedelta(days=1)

    return (
        yesterday_noon.astimezone(timezone.utc).isoformat(),
        today_noon.astimezone(timezone.utc).isoformat()
    )
