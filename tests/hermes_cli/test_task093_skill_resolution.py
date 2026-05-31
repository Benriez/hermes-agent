"""TASK-093 — kanban-worker skill availability regression tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

from hermes_cli import kanban_db as kdb


def _write_skill(home: Path, name: str = "kanban-worker") -> None:
    skill = home / "skills" / "devops" / name / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: kanban-worker\n---\n", encoding="utf-8")


def _task() -> kdb.Task:
    return kdb.Task(
        id="t_task093",
        title="task 093",
        body=None,
        assignee="task093-profile",
        status="running",
        priority=0,
        created_by="test",
        created_at=0,
        started_at=None,
        completed_at=None,
        workspace_kind="scratch",
        workspace_path=None,
        claim_lock="claim",
        claim_expires=None,
        tenant=None,
    )


def test_kanban_worker_available_when_skill_exists_and_not_disabled(tmp_path):
    home = tmp_path / "profile-home"
    _write_skill(home)
    (home / "config.yaml").write_text("skills:\n  disabled: []\n", encoding="utf-8")

    assert kdb._resolve_task_skill_in_home(str(home), "kanban-worker") is True
    assert kdb._kanban_worker_skill_available(str(home)) is True


def test_kanban_worker_unavailable_when_profile_disables_skill(tmp_path):
    home = tmp_path / "profile-home"
    _write_skill(home)
    (home / "config.yaml").write_text(
        "skills:\n  disabled:\n    - kanban-worker\n",
        encoding="utf-8",
    )

    assert kdb._resolve_task_skill_in_home(str(home), "kanban-worker") is False
    assert kdb._kanban_worker_skill_available(str(home)) is False


def test_kanban_worker_unavailable_when_skill_missing(tmp_path):
    home = tmp_path / "profile-home"
    (home / "skills" / "devops").mkdir(parents=True)
    (home / "config.yaml").write_text("skills:\n  disabled: []\n", encoding="utf-8")

    assert kdb._resolve_task_skill_in_home(str(home), "kanban-worker") is False
    assert kdb._kanban_worker_skill_available(str(home)) is False


def test_default_spawn_adds_kanban_worker_only_when_available_and_enabled(
    tmp_path, monkeypatch
):
    home = tmp_path / ".hermes"
    _write_skill(home)
    (home / "config.yaml").write_text("skills:\n  disabled: []\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(kdb, "_resolve_hermes_argv", lambda: ["hermes"])

    captured: list[list[str]] = []

    class FakeProc:
        pid = 4242

    def fake_popen(cmd, **kwargs):
        captured.append(list(cmd))
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    assert kdb._default_spawn(_task(), str(workspace)) == 4242
    skills_index = captured[-1].index("--skills")
    assert ["--skills", "kanban-worker"] == captured[-1][skills_index:skills_index + 2]

    (home / "config.yaml").write_text(
        "skills:\n  disabled:\n    - kanban-worker\n",
        encoding="utf-8",
    )

    assert kdb._default_spawn(_task(), str(workspace)) == 4242
    assert "kanban-worker" not in captured[-1]
