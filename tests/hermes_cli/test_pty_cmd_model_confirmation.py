"""Tests for `/api/pty-cmd` model-switch confirmation contract.

The dashboard's model picker injects ``/model …`` slash commands via
``/api/pty-cmd``.  The backend must wait for the PTY-side gateway to
publish a ``session.info`` confirming the runtime swap before responding,
so the dashboard never has to race a 5s wall-clock timer to decide whether
the runtime actually switched.

Covered:
  * Non-model commands bypass the confirmation path (no regression in latency).
  * Model commands return ``runtime_switched=True`` when the PTY publishes
    the matching ``session.info`` in time.
  * Model commands return ``runtime_switched=False`` +
    ``action_required="stop_runtime_then_rebuild"`` when no confirming
    ``session.info`` arrives — the dashboard uses this to surface an
    actionable restart prompt instead of an opaque "not confirmed in 5s".
  * ``_parse_model_switch_target`` strips ``--provider`` / ``--global`` /
    ``--refresh`` flags so the runtime comparison is on the bare model id.
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def web_server_module(monkeypatch):
    """Import web_server with dashboard chat enabled and a clean state."""
    from hermes_cli import web_server as ws

    # The endpoint is gated by this module-level flag — flip it for the test.
    monkeypatch.setattr(ws, "_DASHBOARD_EMBEDDED_CHAT_ENABLED", True)

    # Drop any cached bridges / runtime info from prior tests.
    ws._pty_bridges.clear()
    ws._last_runtime_info.clear()

    # Tighten the confirmation window so the failure-path tests don't
    # spend 6s waiting.  100ms is plenty for the success path which only
    # needs one poll cycle.
    monkeypatch.setattr(ws, "_MODEL_SWITCH_CONFIRM_S", 0.4)
    monkeypatch.setattr(ws, "_MODEL_SWITCH_POLL_INTERVAL_S", 0.02)

    return ws


def test_parse_model_switch_target_strips_flags(web_server_module):
    parse = web_server_module._parse_model_switch_target
    assert parse("/model kimi-k2.5 --provider opencode-go") == "kimi-k2.5"
    assert parse("/model deepseek-v4-pro --global") == "deepseek-v4-pro"
    assert parse("/model gpt-implementer --refresh") == "gpt-implementer"
    assert parse("/model --provider opencode-go gpt-implementer") == "gpt-implementer"


def test_parse_model_switch_target_returns_none_for_non_model(web_server_module):
    parse = web_server_module._parse_model_switch_target
    assert parse("/profile status") is None
    assert parse("hello world") is None
    # Bare `/model` opens the picker — nothing to confirm against.
    assert parse("/model") is None
    assert parse("/model   ") is None


def test_pty_cmd_non_model_skips_confirmation(web_server_module):
    """Non-/model commands return the legacy fast-path response."""
    ws = web_server_module
    channel = "test-channel-noswitch"
    bridge = MagicMock()
    ws._pty_bridges[channel] = bridge

    body = ws._PtyCmdBody(channel=channel, command="hello\nworld")
    resp = asyncio.get_event_loop().run_until_complete(ws._pty_cmd_impl(body))
    data = json.loads(resp.body)

    assert resp.status_code == 200
    assert data["accepted"] is True
    assert data["command_written"] is True
    assert "is_model_switch" not in data
    assert "runtime_switched" not in data
    bridge.write.assert_called_once()


def test_pty_cmd_model_switch_runtime_confirms(web_server_module):
    """When session.info reports the new model in time, return runtime_switched=True."""
    ws = web_server_module
    channel = "test-channel-confirm"

    # Pre-existing runtime state, used as the "previous_model" snapshot.
    ws._last_runtime_info[channel] = {"model": "deepseek-v4-pro", "provider": "openai-codex"}

    # Bridge.write simulates the PTY accepting the keystrokes; the PTY-side
    # gateway would then process /model and emit session.info via /api/pub,
    # which _broadcast_event mirrors into _last_runtime_info.  We simulate
    # that mirror by patching write to update the cache on a tiny delay.
    bridge = MagicMock()

    def _simulate_runtime_switch(_payload):
        async def _set():
            await asyncio.sleep(0.05)
            async with ws._last_runtime_info_lock:
                ws._last_runtime_info[channel] = {
                    "model": "kimi-k2.5",
                    "provider": "opencode-go",
                }
        asyncio.get_event_loop().create_task(_set())

    bridge.write.side_effect = _simulate_runtime_switch
    ws._pty_bridges[channel] = bridge

    body = ws._PtyCmdBody(
        channel=channel,
        command="/model kimi-k2.5 --provider opencode-go",
    )
    resp = asyncio.get_event_loop().run_until_complete(ws._pty_cmd_impl(body))
    data = json.loads(resp.body)

    assert resp.status_code == 200
    assert data["accepted"] is True
    assert data["is_model_switch"] is True
    assert data["requested_model"] == "kimi-k2.5"
    assert data["previous_model"] == "deepseek-v4-pro"
    assert data["runtime_switched"] is True
    assert data["runtime_model"] == "kimi-k2.5"
    assert data["runtime_provider"] == "opencode-go"
    assert "action_required" not in data


def test_pty_cmd_model_switch_runtime_does_not_confirm(web_server_module):
    """When no session.info arrives, return restart-required structured signal."""
    ws = web_server_module
    channel = "test-channel-noconfirm"

    ws._last_runtime_info[channel] = {"model": "deepseek-v4-pro", "provider": "openai-codex"}

    bridge = MagicMock()  # write is a no-op — runtime "doesn't switch"
    ws._pty_bridges[channel] = bridge

    body = ws._PtyCmdBody(
        channel=channel,
        command="/model kimi-k2.5 --provider opencode-go",
    )
    started = time.monotonic()
    resp = asyncio.get_event_loop().run_until_complete(ws._pty_cmd_impl(body))
    elapsed = time.monotonic() - started
    data = json.loads(resp.body)

    # Must respect the configured deadline (we set 0.4s in the fixture)
    # — never block forever on a runtime that refuses to swap.
    assert elapsed < 2.0
    assert resp.status_code == 200
    assert data["accepted"] is True
    assert data["is_model_switch"] is True
    assert data["runtime_switched"] is False
    assert data["requested_model"] == "kimi-k2.5"
    assert data["previous_model"] == "deepseek-v4-pro"
    # Stale cache is reported as the runtime model — frontend uses this
    # to keep the badge honest instead of pretending the switch worked.
    assert data["runtime_model"] == "deepseek-v4-pro"
    assert data["action_required"] == "stop_runtime_then_rebuild"
    assert "error" in data and "did not switch" in data["error"]


def test_pty_cmd_model_switch_with_no_previous_cache(web_server_module):
    """Switch confirmation works even when no prior session.info was cached."""
    ws = web_server_module
    channel = "test-channel-fresh"

    bridge = MagicMock()

    def _simulate(_payload):
        async def _set():
            await asyncio.sleep(0.05)
            async with ws._last_runtime_info_lock:
                ws._last_runtime_info[channel] = {
                    "model": "kimi-k2.5",
                    "provider": "opencode-go",
                }
        asyncio.get_event_loop().create_task(_set())

    bridge.write.side_effect = _simulate
    ws._pty_bridges[channel] = bridge

    body = ws._PtyCmdBody(channel=channel, command="/model kimi-k2.5")
    resp = asyncio.get_event_loop().run_until_complete(ws._pty_cmd_impl(body))
    data = json.loads(resp.body)

    assert resp.status_code == 200
    assert data["runtime_switched"] is True
    assert data["previous_model"] == ""
    assert data["runtime_model"] == "kimi-k2.5"


def test_pty_cmd_missing_channel_unchanged(web_server_module):
    ws = web_server_module
    body = ws._PtyCmdBody(channel="", command="/model x")
    resp = asyncio.get_event_loop().run_until_complete(ws._pty_cmd_impl(body))
    data = json.loads(resp.body)
    assert resp.status_code == 400
    assert data["accepted"] is False
    # Failure path must NOT advertise an unhonored confirmation contract.
    assert "runtime_switched" not in data


def test_pty_cmd_no_bridge_unchanged(web_server_module):
    ws = web_server_module
    body = ws._PtyCmdBody(channel="no-such-channel", command="/model x")
    resp = asyncio.get_event_loop().run_until_complete(ws._pty_cmd_impl(body))
    data = json.loads(resp.body)
    assert resp.status_code == 404
    assert data["accepted"] is False
    assert "runtime_switched" not in data
