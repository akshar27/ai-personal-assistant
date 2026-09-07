import time

from graph import memory


def test_preferences_round_trip():
    memory.save_preference("u1", "timezone", "America/Los_Angeles")
    memory.save_preference("u1", "user_preference", "prefers concise emails")

    prefs = memory.get_preferences("u1")
    assert {p["key"] for p in prefs} == {"timezone", "user_preference"}
    assert memory.get_latest_preference_value("u1", "timezone") == "America/Los_Angeles"
    assert memory.get_latest_preference_value("u1", "missing") is None


def test_latest_preference_wins():
    memory.save_preference("u1", "timezone", "America/New_York")
    time.sleep(0.01)
    memory.save_preference("u1", "timezone", "Asia/Kolkata")
    assert memory.get_latest_preference_value("u1", "timezone") == "Asia/Kolkata"


def test_preferences_are_scoped_per_user():
    memory.save_preference("a", "user_preference", "a-only")
    assert memory.get_preferences("b") == []


def test_task_lifecycle():
    tid = memory.create_task("u1", "apply to Lyft", due_at="2020-01-01T09:00:00", source="job_search")
    assert isinstance(tid, int)

    open_tasks = memory.get_open_tasks("u1")
    assert len(open_tasks) == 1
    assert open_tasks[0]["title"] == "apply to Lyft"
    assert open_tasks[0]["status"] == "open"

    # a due date in the past shows up as due
    assert any(t["id"] == tid for t in memory.get_due_tasks("u1"))

    assert memory.mark_task_done("u1", tid) is True
    assert memory.get_open_tasks("u1") == []
    # a task id that does not exist for this user is a no-op
    assert memory.mark_task_done("u1", 999999) is False
    assert memory.mark_task_done("other-user", tid) is False


def test_future_task_is_not_due():
    memory.create_task("u1", "later", due_at="2999-01-01T00:00:00")
    assert memory.get_due_tasks("u1") == []


def test_task_without_due_date_is_open_but_not_due():
    memory.create_task("u1", "no deadline")
    assert len(memory.get_open_tasks("u1")) == 1
    assert memory.get_due_tasks("u1") == []
