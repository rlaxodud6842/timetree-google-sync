import unittest

from api import API_BASEURI, TimeTreeApi


class CookieJar(dict):
    def set(self, key, value):
        self[key] = value


class FakeResponse:
    def __init__(self, status_code=200, data=None, text=None, cookies=None):
        self.status_code = status_code
        self._data = data if data is not None else {}
        self.text = text if text is not None else "{}"
        self.cookies = CookieJar()
        if cookies:
            self.cookies.update(cookies)

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.cookies = CookieJar()

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)


class TimeTreeApiTest(unittest.TestCase):
    def test_update_event_sends_partial_payload_to_discovered_endpoint(self):
        session = FakeSession([FakeResponse(data={"event": {"title": "new"}})])
        api = TimeTreeApi(None, "user@example.com", "password", session=session)
        api._session_id = "sid"
        api._csrf_token = "csrf"

        api._update_event(
            1071319023,
            "event-id",
            {
                "summary": "new",
                "description": "notes",
                "start_at": 1,
                "end_at": 2,
                "timezone": "Asia/Tokyo",
            },
        )

        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "PUT")
        self.assertEqual(url, f"{API_BASEURI}/calendar/1071319023/event/event-id")
        self.assertEqual(kwargs["headers"]["X-CSRF-Token"], "csrf")
        self.assertEqual(
            kwargs["json"],
            {
                "end_at": 2,
                "start_at": 1,
                "title": "new",
                "note": "notes",
                "start_timezone": "Asia/Tokyo",
                "end_timezone": "Asia/Tokyo",
            },
        )

    def test_delete_event_sends_delete_without_payload(self):
        session = FakeSession([FakeResponse(data={})])
        api = TimeTreeApi(None, "user@example.com", "password", session=session)
        api._session_id = "sid"
        api._csrf_token = "csrf"

        api._delete_event(1071319023, "event-id")

        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "DELETE")
        self.assertEqual(url, f"{API_BASEURI}/calendar/1071319023/event/event-id")
        self.assertIsNone(kwargs["json"])
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(kwargs["headers"]["X-CSRF-Token"], "csrf")

    def test_update_event_reauths_once_after_401(self):
        session = FakeSession(
            [
                FakeResponse(status_code=401, text="unauthorized"),
                FakeResponse(cookies={"_session_id": "new-sid"}),
                FakeResponse(
                    text='<html><head><meta name="csrf-token" content="new-csrf"></head></html>'
                ),
                FakeResponse(data={"event": {"title": "new"}}),
            ]
        )
        api = TimeTreeApi(None, "user@example.com", "password", session=session)
        api._session_id = "old-sid"
        api._csrf_token = "old-csrf"

        api._update_event(1, "event-id", {"summary": "new"})

        self.assertEqual(session.calls[0][0], "PUT")
        self.assertEqual(session.calls[1][0], "PUT")
        self.assertEqual(session.calls[1][1], f"{API_BASEURI}/auth/email/signin")
        self.assertEqual(session.calls[2][0], "GET")
        self.assertEqual(session.calls[2][1], "https://timetreeapp.com/calendars")
        self.assertEqual(session.calls[3][0], "PUT")
        self.assertEqual(session.calls[3][2]["headers"]["X-CSRF-Token"], "new-csrf")
        self.assertEqual(api.session_id, "new-sid")

    def test_create_event_uses_create_endpoint_and_defaults(self):
        session = FakeSession(
            [
                FakeResponse(data={"user": {"id": 123}}),
                FakeResponse(data={"event": {"title": "created"}}),
            ]
        )
        api = TimeTreeApi(None, "user@example.com", "password", session=session)
        api._session_id = "sid"
        api._csrf_token = "csrf"

        api._create_event(
            "calendar-id",
            {
                "summary": "created",
                "description": "body",
                "start_at": 1000,
                "end_at": 2000,
                "timezone": "UTC",
            },
        )

        self.assertEqual(session.calls[0][0], "GET")
        self.assertEqual(session.calls[0][1], f"{API_BASEURI}/user")

        method, url, kwargs = session.calls[1]
        self.assertEqual(method, "POST")
        self.assertEqual(url, f"{API_BASEURI}/calendar/calendar-id/event")
        self.assertEqual(kwargs["json"]["category"], 1)
        self.assertEqual(kwargs["json"]["label_id"], 1)
        self.assertEqual(kwargs["json"]["title"], "created")
        self.assertEqual(kwargs["json"]["note"], "body")
        self.assertEqual(kwargs["json"]["attendees"], [123])
        self.assertEqual(kwargs["json"]["recurrences"], [])
        self.assertEqual(kwargs["json"]["alerts"], [])
        self.assertEqual(kwargs["json"]["attachment"], {"virtual_user_attendees": []})


if __name__ == "__main__":
    unittest.main()
