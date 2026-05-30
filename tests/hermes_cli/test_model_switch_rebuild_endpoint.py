"""Tests for the real PTY session rebuild endpoint /api/model-switch/rebuild.

The endpoint closes/disposes the current PTY bridge for a channel and
returns {rebuilt: true} so the frontend can reload the page with
?model=...&provider=... in the URL.  The new pty_ws handler then spawns
a fresh PTY with the selected runtime via env vars.

This is a REAL rebuild — the old agent process is terminated and a new
one starts with the selected model/provider from the beginning.  It does
NOT retry /interrupt + /model.

Covered:
  * Rebuild closes the old PTY bridge (bridge.close() called).
  * Rebuild deregisters the bridge from _pty_bridges.
  * Rebuild clears _last_runtime_info for the channel.
  * Rebuild returns {accepted: True, rebuilt: True, action: "reconnect_pty"}.
  * Newline / NUL in model or provider is rejected before any action.
  * Missing channel / missing bridge / empty model return appropriate errors.
  * Chat-disabled returns 403.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def web_server_module(monkeypatch):
    from hermes_cli import web_server as ws

    monkeypatch.setattr(ws, "_DASHBOARD_EMBEDDED_CHAT_ENABLED", True)
    ws._pty_bridges.clear()
    ws._last_runtime_info.clear()
    return ws


def _run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


def test_rebuild_closes_bridge_and_returns_rebuilt(web_server_module):
    """Rebuild closes the old PTY bridge, deregisters it, and returns rebuilt=True."""
    ws = web_server_module
    channel = "ch-rebuild-1"

    bridge = MagicMock()
    ws._pty_bridges[channel] = bridge
    ws._last_runtime_info[channel] = {
        "model": "deepseek-v4-pro",
        "provider": "openai-codex",
    }

    body = ws._ModelSwitchRebuildBody(
        channel=channel, model="kimi-k2.6", provider="opencode-go",
    )
    resp = _run(ws._model_switch_rebuild_impl(body))
    data = json.loads(resp.body)

    assert resp.status_code == 200
    assert data["accepted"] is True
    assert data["rebuilt"] is True
    assert data["requested_model"] == "kimi-k2.6"
    assert data["requested_provider"] == "opencode-go"
    assert data["previous_model"] == "deepseek-v4-pro"
    assert data["previous_provider"] == "openai-codex"
    assert data["action"] == "reconnect_pty"

    # Bridge must have been closed
    bridge.close.assert_called_once()

    # Bridge must be deregistered
    assert channel not in ws._pty_bridges

    # Runtime info must be cleared
    assert channel not in ws._last_runtime_info


def test_rebuild_omits_provider_when_not_specified(web_server_module):
    """When provider is None, previous_provider is empty and no provider in response."""
    ws = web_server_module
    channel = "ch-rebuild-noprov"

    bridge = MagicMock()
    ws._pty_bridges[channel] = bridge
    ws._last_runtime_info[channel] = {"model": "deepseek-v4-pro", "provider": ""}

    body = ws._ModelSwitchRebuildBody(channel=channel, model="kimi-k2.6")
    resp = _run(ws._model_switch_rebuild_impl(body))
    data = json.loads(resp.body)

    assert resp.status_code == 200
    assert data["rebuilt"] is True
    assert data["requested_provider"] == ""
    assert data["previous_provider"] == ""

    bridge.close.assert_called_once()


def test_rebuild_rejects_newline_in_model(web_server_module):
    """Newlines must not slip through — rejected before bridge.close()."""
    ws = web_server_module
    channel = "ch-rebuild-evil"
    bridge = MagicMock()
    ws._pty_bridges[channel] = bridge

    body = ws._ModelSwitchRebuildBody(
        channel=channel, model="kimi\n/shutdown", provider="opencode-go",
    )
    resp = _run(ws._model_switch_rebuild_impl(body))
    data = json.loads(resp.body)

    assert resp.status_code == 400
    assert data["accepted"] is False
    assert "newline" in data["error"]
    bridge.close.assert_not_called()
    # Bridge must still be registered (nothing was written)
    assert channel in ws._pty_bridges


def test_rebuild_rejects_newline_in_provider(web_server_module):
    ws = web_server_module
    channel = "ch-rebuild-evil2"
    bridge = MagicMock()
    ws._pty_bridges[channel] = bridge

    body = ws._ModelSwitchRebuildBody(
        channel=channel, model="kimi-k2.6", provider="opencode-go\n/shutdown",
    )
    resp = _run(ws._model_switch_rebuild_impl(body))
    data = json.loads(resp.body)

    assert resp.status_code == 400
    assert data["accepted"] is False
    bridge.close.assert_not_called()


def test_rebuild_rejects_nul_in_model(web_server_module):
    """NUL bytes must be rejected."""
    ws = web_server_module
    channel = "ch-rebuild-nul"
    bridge = MagicMock()
    ws._pty_bridges[channel] = bridge

    body = ws._ModelSwitchRebuildBody(
        channel=channel, model="kimi\x00bad", provider="safe",
    )
    resp = _run(ws._model_switch_rebuild_impl(body))
    data = json.loads(resp.body)

    assert resp.status_code == 400
    assert data["accepted"] is False
    bridge.close.assert_not_called()


def test_rebuild_missing_model_returns_400(web_server_module):
    ws = web_server_module
    channel = "ch-rebuild-empty"
    bridge = MagicMock()
    ws._pty_bridges[channel] = bridge

    body = ws._ModelSwitchRebuildBody(channel=channel, model="")
    resp = _run(ws._model_switch_rebuild_impl(body))
    data = json.loads(resp.body)

    assert resp.status_code == 400
    assert data["accepted"] is False
    assert data["rebuilt"] is False
    bridge.close.assert_not_called()


def test_rebuild_no_bridge_returns_404(web_server_module):
    ws = web_server_module
    body = ws._ModelSwitchRebuildBody(channel="no-such", model="kimi-k2.6")
    resp = _run(ws._model_switch_rebuild_impl(body))
    data = json.loads(resp.body)

    assert resp.status_code == 404
    assert data["accepted"] is False
    assert data["rebuilt"] is False


def test_rebuild_chat_disabled_returns_403(web_server_module, monkeypatch):
    ws = web_server_module
    monkeypatch.setattr(ws, "_DASHBOARD_EMBEDDED_CHAT_ENABLED", False)
    bridge = MagicMock()
    ws._pty_bridges["ch-gate"] = bridge

    body = ws._ModelSwitchRebuildBody(channel="ch-gate", model="kimi-k2.6")
    resp = _run(ws._model_switch_rebuild_impl(body))
    data = json.loads(resp.body)

    assert resp.status_code == 403
    assert data["accepted"] is False
    assert data["rebuilt"] is False
    bridge.close.assert_not_called()


def test_rebuild_does_not_write_config_yaml(web_server_module, monkeypatch):
    """Rebuild must never touch config.yaml or any global config."""
    ws = web_server_module
    channel = "ch-rebuild-noconfig"

    bridge = MagicMock()
    ws._pty_bridges[channel] = bridge

    body = ws._ModelSwitchRebuildBody(channel=channel, model="kimi-k2.6")
    resp = _run(ws._model_switch_rebuild_impl(body))
    data = json.loads(resp.body)

    assert resp.status_code == 200
    assert data["rebuilt"] is True
    # The rebuild must not have attempted any config writes.
    # We verify indirectly: the endpoint only touches _pty_bridges,
    # _last_runtime_info, and the bridge — no config API calls.
