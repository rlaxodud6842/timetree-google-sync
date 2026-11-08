
from api import TimeTreeApi
from dotenv import load_dotenv
from datetime import date, datetime
from google_calendar import (
    get_calendar_service,
    insert_event,
    update_event,
    delete_event,
    get_existing_timetree_events,
    is_event_changed
)
import os

load_dotenv()


# -------------------------
# 1. TimeTree 일정 가져오기
# -------------------------

api = TimeTreeApi(
    None,
    os.getenv("TIMETREE_EMAIL"),
    os.getenv("TIMETREE_PASSWORD")
)

timetree_calendars = api._get_calendars()
timetree_calendar_id = timetree_calendars[1].get("id")

raw_events = api._get_events(timetree_calendar_id)
events = [api.parse_event(event) for event in raw_events]

if not events:
    raise RuntimeError("TimeTree 일정이 없거나 조회에 실패했습니다.")

print(f"TimeTree 일정 {len(events)}개 조회")


# -------------------------
# 2. 이번 달 일정만 필터링
# -------------------------

today = date.today()

start_date = today.replace(day=1)

if today.month == 12:
    end_date = date(today.year + 1, 1, 1)
else:
    end_date = date(today.year, today.month + 1, 1)


def get_event_date(value):
    return value.date() if isinstance(value, datetime) else value


filtered_events = {
    str(event["id"]): event
    for event in events
    if start_date <= get_event_date(event["start"]) < end_date
}

print(f"이번 달 일정 {len(filtered_events)}개")


# -------------------------
# 3. Google Calendar 연결
# -------------------------

service = get_calendar_service()

GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")


# -------------------------
# 4. 기존 Google 일정 조회
# -------------------------

existing_events = get_existing_timetree_events(
    service,
    GOOGLE_CALENDAR_ID
)


# -------------------------
# 5. 이번 달에 해당하는 기존 일정만 추리기
# -------------------------

def is_in_this_month(item):
    start = item.get("start", {})

    if start.get("date"):
        event_date = date.fromisoformat(start["date"])
    else:
        event_date = datetime.fromisoformat(
            start["dateTime"].replace("Z", "+00:00")
        ).astimezone().date()

    return start_date <= event_date < end_date


existing_this_month = {
    timetree_id: item
    for timetree_id, item in existing_events.items()
    if is_in_this_month(item)
}


# -------------------------
# 6. 신규 일정 및 수정 일정
# -------------------------

added_count = 0
updated_count = 0
unchanged_count = 0

for timetree_id, event in filtered_events.items():

    existing = existing_events.get(timetree_id)

    if existing is None:
        insert_event(service, GOOGLE_CALENDAR_ID, event)
        added_count += 1

    else:
        if is_event_changed(existing, event):
            update_event(
                service,
                GOOGLE_CALENDAR_ID,
                existing["id"],
                event
            )
            updated_count += 1
        else:
            unchanged_count += 1


# -------------------------
# 7. 이번 달 삭제 일정
# -------------------------

deleted_count = 0

for timetree_id, existing in existing_this_month.items():

    if timetree_id not in filtered_events:
        delete_event(
            service,
            GOOGLE_CALENDAR_ID,
            existing["id"]
        )
        deleted_count += 1


# -------------------------
# 8. 결과
# -------------------------

print("\n========== 동기화 결과 ==========")
print(f"신규 등록: {added_count}개")
print(f"일정 수정: {updated_count}개")
print(f"일정 삭제: {deleted_count}개")
print(f"변경 없음: {unchanged_count}개")
print("=================================")
