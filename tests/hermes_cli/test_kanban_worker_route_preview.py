from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hermes_cli import kanban_db as kb
from plugins.kanban.dashboard.plugin_api import router as kanban_router


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


@pytest.fixture
def client(kanban_home):
    app = FastAPI()
    app.include_router(kanban_router)
    return TestClient(app)


def _write_profile(home: Path, name: str, *, provider: str, model: str, api_mode: str = "chat_completions") -> None:
    profile_dir = home / "profiles" / name
    profile_dir.mkdir(parents=True)
    profile_dir.joinpath("config.yaml").write_text(
        "model:\n"
        f"  provider: {provider}\n"
        f"  default: {model}\n"
        f"  api_mode: {api_mode}\n"
        "fallback_providers:\n"
        "  - provider: custom\n"
        "    model: qwopus-27b-mtp-64k\n",
        encoding="utf-8",
    )


def _create_task(assignee: str = "nvidia-implementer") -> str:
    conn = kb.connect()
    try:
        return kb.create_task(
            conn,
            title="Worker route preview target",
            assignee=assignee,
            initial_status="blocked",
            created_by="test",
        )
    finally:
        conn.close()


def test_patch_task_model_override_persists(client, kanban_home):
    task_id = _create_task()

    response = client.patch(f"/tasks/{task_id}", json={"model_override": "override-model"})

    assert response.status_code == 200, response.text
    conn = kb.connect()
    try:
        assert kb.get_task(conn, task_id).model_override == "override-model"
    finally:
        conn.close()


def test_route_preview_uses_assignee_profile_model_provider(client, kanban_home):
    _write_profile(
        kanban_home,
        "nvidia-implementer",
        provider="nvidia",
        model="deepseek-ai/deepseek-v4-pro",
    )
    task_id = _create_task()

    response = client.get(f"/tasks/{task_id}/route-preview")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["task_id"] == task_id
    assert data["assignee"] == "nvidia-implementer"
    assert data["profile"] == "nvidia-implementer"
    assert data["effective_provider"] == "nvidia"
    assert data["effective_model"] == "deepseek-ai/deepseek-v4-pro"
    assert data["api_mode"] == "chat_completions"
    assert data["fallback_providers"] == [{"provider": "custom", "model": "qwopus-27b-mtp-64k"}]
    assert "hermes -p nvidia-implementer --accept-hooks" in data["command_preview"]
    assert f"work kanban task {task_id}" in data["command_preview"]


def test_route_preview_includes_model_override_flag(client, kanban_home):
    _write_profile(
        kanban_home,
        "nvidia-implementer",
        provider="nvidia",
        model="deepseek-ai/deepseek-v4-pro",
    )
    task_id = _create_task()
    assert client.patch(f"/tasks/{task_id}", json={"model_override": "custom-model"}).status_code == 200

    response = client.get(f"/tasks/{task_id}/route-preview")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["model_override"] == "custom-model"
    assert data["effective_model"] == "custom-model"
    assert " -m custom-model " in data["command_preview"]


def test_route_preview_warns_on_default_assignee(client, kanban_home):
    (kanban_home / "config.yaml").write_text(
        "model:\n  provider: custom\n  default: root-model\n",
        encoding="utf-8",
    )
    task_id = _create_task(assignee="default")

    response = client.get(f"/tasks/{task_id}/route-preview")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["profile"] == "default"
    assert "Worker will use DEFAULT profile" in data["warnings"]


def test_route_preview_does_not_change_status_or_create_run(client, kanban_home):
    _write_profile(
        kanban_home,
        "nvidia-implementer",
        provider="nvidia",
        model="deepseek-ai/deepseek-v4-pro",
    )
    task_id = _create_task()
    conn = kb.connect()
    try:
        before_status = kb.get_task(conn, task_id).status
        before_runs = conn.execute("SELECT COUNT(*) FROM task_runs WHERE task_id = ?", (task_id,)).fetchone()[0]
    finally:
        conn.close()

    response = client.get(f"/tasks/{task_id}/route-preview")

    assert response.status_code == 200, response.text
    conn = kb.connect()
    try:
        assert kb.get_task(conn, task_id).status == before_status == "blocked"
        after_runs = conn.execute("SELECT COUNT(*) FROM task_runs WHERE task_id = ?", (task_id,)).fetchone()[0]
        assert after_runs == before_runs == 0
    finally:
        conn.close()
