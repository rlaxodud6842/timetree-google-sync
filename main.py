
from api import TimeTreeApi
from dotenv import load_dotenv

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
# 1. TimeTree 연결
# -------------------------

api = TimeTreeApi(
    None,
    os.getenv("TIMETREE_EMAIL"),
    os.getenv("TIMETREE_PASSWORD")
)

timetree_calendars = api._get_calendars()

if len(timetree_calendars) <= 1:
    raise RuntimeError("TimeTree 캘린더를 찾을 수 없습니다.")

timetree_calendar_id = timetree_calendars[1].get("id")

if not timetree_calendar_id:
    raise RuntimeError("TimeTree 캘린더 ID가 없습니다.")


# -------------------------
# 2. TimeTree 일정 전체 조회
# -------------------------

raw_events = api._get_events(timetree_calendar_id)

if raw_events is None:
    raise RuntimeError("TimeTree 일정 조회에 실패했습니다.")

events = [
    api.parse_event(event)
    for event in raw_events
]

if not events:
    raise RuntimeError(
        "TimeTree 일정이 0개 조회되었습니다. "
        "잘못된 전체 삭제를 방지하기 위해 동기화를 중단합니다."
    )

# ID 중복 방지
timetree_events = {
    str(event["id"]): event
    for event in events
}

print(f"TimeTree 일정 {len(timetree_events)}개 조회 완료")


# -------------------------
# 3. Google Calendar 연결
# -------------------------

service = get_calendar_service()

GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

if not GOOGLE_CALENDAR_ID:
    raise RuntimeError("GOOGLE_CALENDAR_ID가 설정되지 않았습니다.")


# -------------------------
# 4. 기존 동기화 일정 조회
# -------------------------

existing_events = get_existing_timetree_events(
    service,
    GOOGLE_CALENDAR_ID
)

print(f"기존 Google Calendar 동기화 일정 {len(existing_events)}개 조회")


# -------------------------
# 5. 신규 일정 및 수정 일정 처리
# -------------------------

added_count = 0
updated_count = 0
unchanged_count = 0

for timetree_id, event in timetree_events.items():

    existing = existing_events.get(timetree_id)

    # 신규 일정
    if existing is None:
        insert_event(
            service,
            GOOGLE_CALENDAR_ID,
            event
        )
        added_count += 1

    # 기존 일정
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
# 6. 삭제된 일정 처리
# -------------------------

deleted_count = 0

for timetree_id, existing in existing_events.items():

    # TimeTree에 더 이상 존재하지 않는 일정
    if timetree_id not in timetree_events:

        delete_event(
            service,
            GOOGLE_CALENDAR_ID,
            existing["id"]
        )

        deleted_count += 1


# -------------------------
# 7. 결과 출력
# -------------------------

print("\n========== 동기화 결과 ==========")
print(f"신규 등록: {added_count}개")
print(f"일정 수정: {updated_count}개")
print(f"일정 삭제: {deleted_count}개")
print(f"변경 없음: {unchanged_count}개")
print("=================================")

print("동기화 완료!")
