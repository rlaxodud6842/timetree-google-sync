from api import TimeTreeApi
from dotenv import load_dotenv
from datetime import date, datetime
from google_calendar import (
    get_calendar_service,
    insert_event,
    get_existing_timetree_ids
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

print(f"TimeTree 일정 {len(events)}개 조회")


# -------------------------
# 2. 이번 달 일정 필터링
# -------------------------


today = date.today()
start_date = today.replace(day=1)

if today.month == 12:
    end_date = date(today.year + 1, 1, 1)
else:
    end_date = date(today.year, today.month + 1, 1)

filtered_events = [
    event for event in events
    if start_date <= (
        event["start"].date()
        if isinstance(event["start"], datetime)
        else event["start"]
    ) < end_date
]

# -------------------------
# 3. Google Calendar 연결
# -------------------------

service = get_calendar_service()

# 네가 찾은 Google Calendar ID 입력
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")


# -------------------------
# 4. 기존 등록 일정 확인
# -------------------------

existing_ids = get_existing_timetree_ids(
    service,
    GOOGLE_CALENDAR_ID
)


# -------------------------
# 5. 신규 일정 등록
# -------------------------

for event in filtered_events:

    event_id = str(event["id"])

    if event_id in existing_ids:
        print("이미 등록됨:", event["summary"])
        continue

    insert_event(service, GOOGLE_CALENDAR_ID, event)

print("동기화 완료!")
