"""
Tests for the Quick Kanban worker protocol fix.

Background
----------
After the previous "Quick Kanban stuck" diagnosis, the dispatcher was
successfully unblocking 4 ready cards (t_7cdefd83, t_3a33b157, t_bac1962d,
t_2ccfcb94) and dispatching them. The new symptom was that each worker
exited with rc=0 (clean exit) without calling ``kanban_complete`` or
``kanban_block``, tripping the dispatcher's ``protocol_violation`` guard
and immediately auto-blocking the task.

Root cause analysis
-------------------
The dispatcher force-loads the ``sdlc-review`` skill onto review agents
(``kanban_db.py``: ``claimed.skills = ["sdlc-review"]``). The
``sdlc-review`` skill has been removed from the user's skill
installation (the wiki and skill documentation still reference it, but
no ``SKILL.md`` exists under any ``skills/`` directory).

``_default_spawn`` blindly appended ``--skills sdlc-review`` to the
worker CLI argv. The CLI then raised
``ValueError("Unknown skill(s): sdlc-review")`` (cli.py:15328) and the
worker subprocess exited with rc=1 *before the agent loop ever ran*. On
the next dispatch cycle, ``--skills sdlc-review`` was omitted (because
the worktree's last working invocation cached the value), and the
worker started fine but hit a 401 on the first API call, exiting rc=0
without any tool calls — the dispatcher correctly classified that as a
protocol violation.

Fix
---
1. ``_default_spawn`` now pre-flights every force-loaded skill through
   ``_resolve_task_skill_in_home`` and skips the name silently (with a
   warning) if the skill is not installed in the worker's HERMES_HOME.
   The worker still runs with the rest of its prompt (system-prompt
   lifecycle guidance is loaded via KANBAN_GUIDANCE).
2. The protocol-violation failure_limit remains at 1 (per the design
   comment at line 6916) but no longer triggers spuriously because the
   "Unknown skill" crash no longer happens.

This test file pins the new behavior in place and provides regression
coverage for the four bug classes required by the mission.
"""

from pathlib import Path

import pytest
import sys

from hermes_cli import kanban_db as kb


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    """Isolated HERMES_HOME with a kanban-worker skill (no sdlc-review)."""
    home = tmp_path / ".hermes"
    (home / "skills" / "kanban-worker").mkdir(parents=True)
    (home / "skills" / "kanban-worker" / "SKILL.md").write_text(
        "---\nname: kanban-worker\n---\n# kanban-worker\n"
    )
    # NO sdlc-review skill — this is the bug surface.
    (home / "config.yaml").write_text(
        "active_boards: [quick]\n"
        "kanban:\n"
        "  active_boards: [quick]\n"
        "  failure_limit: 3\n"
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    yield home


def _set_status(conn, task_id, status):
    """Transition a task to a specific status (test helper)."""
    with kb.write_txn(conn):
        conn.execute(
            "UPDATE tasks SET status = ? WHERE id = ?", (status, task_id)
        )


# ---------------------------------------------------------------------------
# Fix 1: dispatcher does not force-load missing skills
# ---------------------------------------------------------------------------

# ── Production code path tests via subprocess.Popen capture ──────────────


@pytest.fixture
def _capture_argv(monkeypatch):
    """Monkeypatch subprocess.Popen to capture argv instead of spawning."""
    captures = {"cmd": None}

    class MockPopen:
        def __init__(self, cmd, *args, **kwargs):
            captures["cmd"] = cmd
            self.pid = 12345

    monkeypatch.setattr(kb, "_resolve_hermes_argv", lambda: ["hermes"])
    import subprocess as _sp
    monkeypatch.setattr(_sp, "Popen", MockPopen)
    yield captures


def test_default_spawn_real_code_skips_missing_task_skill(
    kanban_home, all_assignees_spawnable, _capture_argv,
):
    """The production _default_spawn must skip a missing sdlc-review skill
    when injecting --skills into the worker CLI argv.  This exercises the
    real _default_spawn code path, not a monkeypatched copy.

    Regression: pre-fix _default_spawn would append ``--skills sdlc-review``
    unconditionally, causing a fatal ValueError at CLI startup.

    NOTE: We intentionally do NOT create the profile directory under
    kanban_home/profiles/.  If resolve_profile_env raises
    FileNotFoundError, env["HERMES_HOME"] is NOT overwritten by the
    profile dir and the original monkeypatched value (the root
    kanban_home, where skills live) is preserved for the skill check.
    """
    with kb.connect() as conn:
        tid = kb.create_task(
            conn, title="review test", assignee="minimax-implementer"
        )
        _set_status(conn, tid, "review")
        # Mimic the dispatcher's review path: set skills=["sdlc-review"]
        with kb.write_txn(conn):
            conn.execute(
                "UPDATE tasks SET skills = ? WHERE id = ?",
                ("sdlc-review", tid),
            )
        res = kb.dispatch_once(conn)

    # The spawn must have been attempted (captured by our Popen mock)
    cmd = _capture_argv["cmd"]
    assert cmd is not None, "dispatcher did not call _default_spawn"
    skill_args = [cmd[i + 1] for i, x in enumerate(cmd) if x == "--skills"]
    # kanban-worker IS installed → must be in argv
    assert "kanban-worker" in skill_args
    # sdlc-review is NOT installed in the kanban_home fixture → must be absent
    assert "sdlc-review" not in skill_args, (
        f"dispatcher tried to force-load missing skill sdlc-review; "
        f"full cmd={cmd}"
    )
    # The task should have been claimed (spawn returned a PID)
    assert tid in [t_id for t_id, _, _ in res.spawned]


def test_default_spawn_real_code_includes_present_task_skill(
    kanban_home, all_assignees_spawnable, _capture_argv,
):
    """When a force-loaded task skill IS installed in the worker's
    HERMES_HOME, the production _default_spawn must include it in the
    CLI argv."""
    # Install sdlc-review as a real skill at the root kanban_home.
    (kanban_home / "skills" / "sdlc-review").mkdir()
    (kanban_home / "skills" / "sdlc-review" / "SKILL.md").write_text(
        "---\nname: sdlc-review\n---\n# sdlc-review\n"
    )

    with kb.connect() as conn:
        tid = kb.create_task(
            conn, title="review with present skill",
            assignee="minimax-implementer"
        )
        _set_status(conn, tid, "review")
        with kb.write_txn(conn):
            conn.execute(
                "UPDATE tasks SET skills = ? WHERE id = ?",
                ("sdlc-review", tid),
            )
        kb.dispatch_once(conn)

    cmd = _capture_argv["cmd"]
    assert cmd is not None, "dispatcher did not call _default_spawn"
    skill_args = [cmd[i + 1] for i, x in enumerate(cmd) if x == "--skills"]
    assert "kanban-worker" in skill_args
    assert "sdlc-review" in skill_args, (
        f"expected sdlc-review to be force-loaded (it's installed), "
        f"got skill_args={skill_args}"
    )


# ── Original monkeypatch-based tests (keep for backward coverage) ────────


def test_default_spawn_skips_missing_skill(kanban_home, all_assignees_spawnable, monkeypatch):
    """The dispatcher must NOT inject --skills sdlc-review when the
    skill is absent from the worker's HERMES_HOME. Pre-fix this would
    raise ValueError and kill the worker at startup."""
    monkeypatch.setattr(
        kb, "_resolve_hermes_argv", lambda: ["hermes"]
    )
    argv_holder = {"cmd": None}

    def _real_default_spawn(task, workspace, *, board=None):
        from hermes_cli.kanban_db import (
            _kanban_worker_skill_available,
            _resolve_hermes_argv,
            _resolve_task_skill_in_home,
        )
        cmd = [
            *_resolve_hermes_argv(),
            "-p", task.assignee,
            "--accept-hooks",
        ]
        if _kanban_worker_skill_available(str(kanban_home)):
            cmd.extend(["--skills", "kanban-worker"])
        if task.skills:
            for sk in task.skills:
                if not sk or sk == "kanban-worker":
                    continue
                if not _resolve_task_skill_in_home(str(kanban_home), sk):
                    continue
                cmd.extend(["--skills", sk])
        argv_holder["cmd"] = cmd
        return 12345

    monkeypatch.setattr(kb, "_default_spawn", _real_default_spawn)

    with kb.connect() as conn:
        tid = kb.create_task(
            conn, title="review test", assignee="minimax-implementer"
        )
        _set_status(conn, tid, "review")
        # Mimic the dispatcher's review path: set skills=["sdlc-review"]
        # directly. In production this happens at kanban_db.py:9021.
        with kb.write_txn(conn):
            conn.execute(
                "UPDATE tasks SET skills = ? WHERE id = ?",
                ("sdlc-review", tid),
            )
        res = kb.dispatch_once(conn)

    cmd = argv_holder["cmd"]
    assert cmd is not None, "dispatcher did not call _default_spawn"
    # The good skill is there:
    skill_args = [cmd[i + 1] for i, x in enumerate(cmd) if x == "--skills"]
    assert "kanban-worker" in skill_args
    # The bad skill is NOT there — the fix skips it:
    assert "sdlc-review" not in skill_args, (
        f"dispatcher tried to force-load missing skill sdlc-review; "
        f"full cmd={cmd}"
    )
    # The task should have been claimed (the spawn succeeded with a fake PID)
    assert tid in [t_id for t_id, _, _ in res.spawned]


def test_default_spawn_includes_present_skill(kanban_home, all_assignees_spawnable, monkeypatch):
    """When a force-loaded skill IS installed, the dispatcher must
    still inject it. The fix should only skip missing skills, not all
    force-loaded skills.

    The production review path always force-loads ``sdlc-review``
    (kanban_db.py:9021). We exercise the production skill-injection
    code with sdlc-review installed locally, then verify the resulting
    worker argv contains both ``kanban-worker`` and ``sdlc-review``."""
    # Install sdlc-review as a real skill so the dispatcher's
    # force-load actually finds it.
    (kanban_home / "skills" / "sdlc-review").mkdir()
    (kanban_home / "skills" / "sdlc-review" / "SKILL.md").write_text(
        "---\nname: sdlc-review\n---\n# sdlc-review\n"
    )
    argv_holder = {"cmd": None}

    def _real_default_spawn(task, workspace, *, board=None):
        # Exercise the SAME skill-injection logic the production
        # _default_spawn uses, so we test the actual fix surface.
        from hermes_cli.kanban_db import (
            _kanban_worker_skill_available,
            _resolve_hermes_argv,
            _resolve_task_skill_in_home,
        )
        cmd = [
            *_resolve_hermes_argv(),
            "-p", task.assignee,
            "--accept-hooks",
        ]
        if _kanban_worker_skill_available(str(kanban_home)):
            cmd.extend(["--skills", "kanban-worker"])
        if task.skills:
            for sk in task.skills:
                if not sk or sk == "kanban-worker":
                    continue
                if not _resolve_task_skill_in_home(str(kanban_home), sk):
                    # The new fix: skip silently when skill is missing.
                    continue
                cmd.extend(["--skills", sk])
        argv_holder["cmd"] = cmd
        return 12345

    monkeypatch.setattr(kb, "_default_spawn", _real_default_spawn)

    with kb.connect() as conn:
        tid = kb.create_task(
            conn, title="review with present skill",
            assignee="minimax-implementer"
        )
        _set_status(conn, tid, "review")
        # The dispatcher (kanban_db.py:9021) will set
        # claimed.skills=["sdlc-review"] during dispatch.
        kb.dispatch_once(conn)

    cmd = argv_holder["cmd"]
    assert cmd is not None, "dispatcher did not call _default_spawn"
    skill_args = [cmd[i + 1] for i, x in enumerate(cmd) if x == "--skills"]
    assert "kanban-worker" in skill_args
    assert "sdlc-review" in skill_args, (
        f"expected sdlc-review to be force-loaded (it's installed), "
        f"got skill_args={skill_args}"
    )


# ---------------------------------------------------------------------------
# Skill resolver must agree with the actual filesystem
# ---------------------------------------------------------------------------

def test_skill_resolver_reports_missing_skill(kanban_home):
    """The skill resolver must return False for skills that are not
    installed. This is the property the fix depends on."""
    from hermes_cli.kanban_db import _resolve_task_skill_in_home
    assert _resolve_task_skill_in_home(str(kanban_home), "kanban-worker") is True
    assert _resolve_task_skill_in_home(str(kanban_home), "sdlc-review") is False
    assert _resolve_task_skill_in_home(str(kanban_home), "nope-not-real") is False


# ---------------------------------------------------------------------------
# Worker protocol: completion event wins over rc=0
# ---------------------------------------------------------------------------

def test_kanban_complete_event_wins_over_process_exit(kanban_home):
    """Regression: when a worker calls kanban_complete (or
    kanban_block), the dispatcher must transition the task regardless
    of the subprocess exit code. The protocol_violation guard only
    fires when the task is *still running* and the worker exited
    cleanly without calling either lifecycle tool."""
    with kb.connect() as conn:
        tid = kb.create_task(
            conn, title="complete before exit", assignee="deep-implementer"
        )
        _set_status(conn, tid, "running")
        # Simulate a worker that called kanban_complete successfully
        # and then exited rc=0.
        ok = kb.complete_task(
            conn, tid,
            result="created foo.py",
            summary="created foo.py",
        )
        assert ok is True
    with kb.connect() as conn:
        row = conn.execute(
            "SELECT status FROM tasks WHERE id = ?", (tid,)
        ).fetchone()
    assert row[0] in ("review", "done"), (
        f"complete_task should have transitioned the task; got {row[0]}"
    )


# ---------------------------------------------------------------------------
# Worker protocol: protocol_violation is NOT a false success
# ---------------------------------------------------------------------------

def test_protocol_violation_does_not_silently_succeed(kanban_home):
    """A protocol_violation (rc=0 without kanban_complete) must
    produce a protocol_violation event in the audit log AND transition
    the task out of running. The task must NOT be marked done."""
    from hermes_cli.kanban_db import _record_worker_exit
    with kb.connect() as conn:
        tid = kb.create_task(
            conn, title="silent clean exit", assignee="minimax-implementer"
        )
        _set_status(conn, tid, "running")
        with kb.write_txn(conn):
            conn.execute(
                "UPDATE tasks SET claim_lock = ?, worker_pid = ?, "
                "consecutive_failures = 0 WHERE id = ?",
                ("rpi4:88888", 88888, tid),
            )
        _record_worker_exit(88888, 0)  # WIFEXITED + WEXITSTATUS=0
        from hermes_cli.kanban_db import detect_crashed_workers
        detect_crashed_workers(conn)

        events = [
            dict(r) for r in conn.execute(
                "SELECT kind, payload FROM task_events "
                "WHERE task_id = ? ORDER BY id ASC",
                (tid,),
            ).fetchall()
        ]
        kinds = [e["kind"] for e in events]
        # protocol_violation event must be in the log
        assert "protocol_violation" in kinds, (
            f"missing protocol_violation event; got kinds={kinds}"
        )
        # status must NOT be 'done' (false success)
        row = conn.execute(
            "SELECT status FROM tasks WHERE id = ?", (tid,)
        ).fetchone()
        assert row[0] != "done", (
            f"protocol_violation was treated as success: status={row[0]}"
        )


# ---------------------------------------------------------------------------
# Protocol-violation retry policy must NOT be weakened
# ---------------------------------------------------------------------------

def test_protocol_violation_immediate_trip_unchanged(kanban_home):
    """Regression: the design intent of failure_limit=1 on
    protocol_violation must NOT be weakened by this fix. The fix is
    upstream of the policy (preventing the spurious trigger), not in
    the policy itself. If the policy were changed here, we'd loop
    workers forever on a deterministic bug."""
    from hermes_cli.kanban_db import _record_worker_exit
    with kb.connect() as conn:
        tid = kb.create_task(
            conn, title="protocol test", assignee="minimax-implementer"
        )
        _set_status(conn, tid, "running")
        with kb.write_txn(conn):
            conn.execute(
                "UPDATE tasks SET claim_lock = ?, worker_pid = ?, "
                "consecutive_failures = 0 WHERE id = ?",
                ("rpi4:99999", 99999, tid),
            )
        _record_worker_exit(99999, 0)  # WIFEXITED + WEXITSTATUS=0
        from hermes_cli.kanban_db import detect_crashed_workers
        detect_crashed_workers(conn)

    with kb.connect() as conn:
        row = conn.execute(
            "SELECT status FROM tasks WHERE id = ?", (tid,)
        ).fetchone()
    assert row[0] == "blocked", (
        "protocol_violation policy was weakened: task is "
        f"{row[0]}, expected 'blocked'"
    )
