from __future__ import annotations

from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_KANBAN_CRASH_GRACE_SECONDS", "0")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


def test_classify_worker_log_detects_429_too_many_requests(tmp_path):
    log = tmp_path / "worker.log"
    log.write_text("provider error: 429 Too Many Requests; retry-after: 60\n", encoding="utf-8")

    assert kb._classify_worker_log_failure(log) == "RATE_LIMIT"


def test_classify_worker_log_detects_insufficient_quota(tmp_path):
    log = tmp_path / "worker.log"
    log.write_text("NVIDIA API error: insufficient_quota for this account\n", encoding="utf-8")

    assert kb._classify_worker_log_failure(log) == "RATE_LIMIT"


def test_classify_worker_log_ignores_normal_errors(tmp_path):
    log = tmp_path / "worker.log"
    log.write_text("Traceback: ValueError: ordinary test failure\n", encoding="utf-8")

    assert kb._classify_worker_log_failure(log) is None


def test_detect_crashed_workers_blocks_rate_limited_task(kanban_home):
    conn = kb.connect()
    try:
        tid = kb.create_task(conn, title="rate limited task", assignee="nvidia-implementer")
        claimed = kb.claim_task(conn, tid)
        assert claimed is not None
        pid = 987654321
        kb._set_worker_pid(conn, tid, pid)
        kb._record_worker_exit(pid, 1 << 8)
        log_path = kb.worker_log_path(tid)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "OpenAI-compatible provider returned 429 rate limit exceeded\n",
            encoding="utf-8",
        )

        crashed = kb.detect_crashed_workers(conn)

        assert tid in crashed
        task = kb.get_task(conn, tid)
        assert task is not None
        assert task.status == "blocked"
        assert task.assignee == "nvidia-implementer"
        assert task.last_failure_error and "RATE_LIMIT" in task.last_failure_error
        assert task.consecutive_failures == 0
        runs = kb.list_runs(conn, tid)
        assert runs[-1].outcome == "blocked"
        assert runs[-1].error and "RATE_LIMIT" in runs[-1].error
        events = kb.list_events(conn, tid)
        assert "rate_limited" in [event.kind for event in events]
        combined_payload = "\n".join(str(event.payload) for event in events)
        assert "local-implementer" in combined_payload
        comments = kb.list_comments(conn, tid)
        assert any("RATE_LIMIT" in comment.body for comment in comments)
        assert any("local-implementer" in comment.body for comment in comments)
    finally:
        conn.close()


def test_detect_crashed_workers_normal_nonzero_crash_still_requeues(kanban_home):
    conn = kb.connect()
    try:
        tid = kb.create_task(conn, title="normal crash", assignee="worker")
        claimed = kb.claim_task(conn, tid)
        assert claimed is not None
        pid = 987654322
        kb._set_worker_pid(conn, tid, pid)
        kb._record_worker_exit(pid, 1 << 8)
        log_path = kb.worker_log_path(tid)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "Traceback: RuntimeError: ordinary failure\n",
            encoding="utf-8",
        )

        crashed = kb.detect_crashed_workers(conn)

        assert tid in crashed
        task = kb.get_task(conn, tid)
        assert task is not None
        assert task.status == "ready"
        assert task.assignee == "worker"
        assert task.consecutive_failures == 1
        assert task.last_failure_error and "RATE_LIMIT" not in task.last_failure_error
        events = kb.list_events(conn, tid)
        assert "crashed" in [event.kind for event in events]
        assert "rate_limited" not in [event.kind for event in events]
    finally:
        conn.close()
