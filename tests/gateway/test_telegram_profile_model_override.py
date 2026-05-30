"""Regression tests for Telegram /profile model/provider override and
orchestrator routing interaction.

Verifies fix: explicit user /profile selection via Telegram must not be
silently cleared or overwritten by the telegram-router plugin's
pre_gateway_dispatch hook.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest


# ──────────────────────────────────────────────────────────────────
# Helper: build a minimal mock gateway for testing
# ──────────────────────────────────────────────────────────────────

def _make_mock_gateway(session_key="agent:main:telegram:dm:123"):
    """Create a mock gateway with _session_model_overrides support."""
    gw = MagicMock()
    gw._session_model_overrides = {}
    gw._evict_cached_agent = MagicMock()
    gw._session_key_for_source = MagicMock(return_value=session_key)
    return gw


def _make_mock_event(text="/profile testprof"):
    """Create a minimal MessageEvent-like object with Telegram platform."""
    ev = MagicMock()
    ev.text = text
    ev.source = MagicMock()
    ev.source.platform = MagicMock()
    ev.source.platform.value = "telegram"
    ev.get_command_args = MagicMock(return_value="testprof")
    ev.message_id = "m99"
    return ev


def _import_plugin():
    """Import the telegram-router plugin, ensuring it's on sys.path."""
    import sys
    from pathlib import Path
    _plugin_path = str(Path.home() / ".hermes" / "plugins" / "telegram-router")
    if _plugin_path not in sys.path:
        sys.path.insert(0, _plugin_path)

    from importlib import import_module
    try:
        return import_module("__init__")
    except ImportError:
        import __init__ as mod
        return mod


# ──────────────────────────────────────────────────────────────────
# Gateway-level: _handle_profile_command stores explicit marker
# ──────────────────────────────────────────────────────────────────

class TestGatewayProfileStoresExplicitMarker:

    def test_override_includes_explicit_and_source(self, monkeypatch):
        """Gateway /profile <name> stores explicit=True and source marker."""
        monkeypatch.setattr(
            "gateway.telegram_orchestrator_routing.resolve_profile_name",
            lambda raw: {"status": "found", "canonical": "testprof", "available": []},
        )
        monkeypatch.setattr(
            "gateway.telegram_orchestrator_routing.load_profile_model_config",
            lambda name: {"model": "test-model", "provider": "test-provider"},
        )
        monkeypatch.setattr(
            "hermes_cli.profiles.get_active_profile_name",
            lambda: "default",
        )
        monkeypatch.setattr(
            "hermes_constants.display_hermes_home",
            lambda: "/home/test/.hermes",
        )

        from gateway.platforms.base import MessageEvent
        from gateway.session import SessionSource

        source = SessionSource(
            platform="telegram", user_id="123", chat_id="123",
            user_name="test", chat_type="dm",
        )
        event = MessageEvent(
            text="/profile testprof",
            message_id="m99",
            source=source,
        )

        gw = _make_mock_gateway()
        gw.config = {"model": {"default": "base-model", "provider": "base"}}
        gw._agent_cache = {}

        from gateway.run import GatewayRunner

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                GatewayRunner._handle_profile_command(gw, event)
            )
        finally:
            loop.close()

        assert result, "Expected non-None result"
        assert "PROFILE_ACTIVATED" in result
        assert "testprof" in result

        # The override must be stored with explicit markers
        assert "agent:main:telegram:dm:123" in gw._session_model_overrides
        override = gw._session_model_overrides["agent:main:telegram:dm:123"]
        assert override.get("explicit") is True, (
            f"Expected explicit=True in override, got {override!r}"
        )
        assert override.get("source") == "telegram:/profile", (
            f"Expected source='telegram:/profile', got {override!r}"
        )
        assert override.get("model") == "test-model"
        assert override.get("provider") == "test-provider"

    def test_invalid_profile_does_not_set_override(self, monkeypatch):
        """Gateway /profile <missing> does not set any override."""
        monkeypatch.setattr(
            "gateway.telegram_orchestrator_routing.resolve_profile_name",
            lambda raw: {"status": "not_found", "canonical": None,
                          "available": [], "reason": "no match"},
        )
        monkeypatch.setattr(
            "hermes_cli.profiles.get_active_profile_name",
            lambda: "default",
        )
        monkeypatch.setattr(
            "hermes_constants.display_hermes_home",
            lambda: "/home/test/.hermes",
        )

        from gateway.platforms.base import MessageEvent
        from gateway.session import SessionSource

        source = SessionSource(
            platform="telegram", user_id="123", chat_id="123",
            user_name="test", chat_type="dm",
        )
        event = MessageEvent(
            text="/profile missing",
            message_id="m100",
            source=source,
        )

        gw = _make_mock_gateway()
        gw.config = {}
        gw._agent_cache = {}

        from gateway.run import GatewayRunner

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                GatewayRunner._handle_profile_command(gw, event)
            )
        finally:
            loop.close()

        assert result, "Expected non-None error result"
        assert "PROFILE_NOT_FOUND" in result
        assert "agent:main:telegram:dm:123" not in gw._session_model_overrides


# ──────────────────────────────────────────────────────────────────
# Plugin-level: _pre_gateway_dispatch respects explicit marker
# ──────────────────────────────────────────────────────────────────

class TestPluginRespectsExplicitOverride:
    """Tests that the telegram-router plugin preserves explicit user overrides.

    IMPORTANT: The plugin imports functions from gateway.telegram_orchestrator_routing
    at module level.  To control behaviour we monkeypatch the plugin module's local
    references directly rather than the source module — this avoids cross-test
    leakage through Python's module caching.
    """

    # ── helpers ──────────────────────────────────────────────────

    def _patch_plugin_for_status(self, mod):
        """Configure the plugin module to classify everything as 'status'."""
        mod.classify_telegram_intent = lambda text: "status"
        mod.load_telegram_orchestrator_policy = lambda: {
            "routing": [
                {"intent": "status", "profile": "default", "description": "general"},
            ]
        }
        mod.select_profile_for_intent = lambda intent, policy: (
            policy["routing"][0]
        )

    def _patch_plugin_for_specialist(self, mod, intent="audit", profile="nvidia-auditor"):
        """Configure the plugin module to classify as a specialist intent."""
        mod.classify_telegram_intent = lambda text: intent
        mod.load_telegram_orchestrator_policy = lambda: {
            "routing": [
                {
                    "intent": intent,
                    "profile": profile,
                    "requires_specialist": True,
                },
                {"intent": "status", "profile": "default"},
            ]
        }
        mod.select_profile_for_intent = lambda intent_arg, policy: next(
            r for r in policy["routing"] if r["intent"] == intent_arg
        )
        mod.format_routing_decision = lambda i, p: f"[routing: {i} -> {p}]"
        mod.load_profile_model_config = lambda name: {
            "model": "new-specialist", "provider": "new-prov",
        }

    # ── tests ────────────────────────────────────────────────────

    def test_status_intent_preserves_explicit_override(self):
        """A status-classified message does NOT clear an explicit /profile override."""
        session_key = "agent:main:telegram:dm:123"
        gw = _make_mock_gateway(session_key=session_key)
        gw._session_model_overrides[session_key] = {
            "model": "explicit-model",
            "provider": "explicit-provider",
            "profile_name": "myprof",
            "explicit": True,
            "source": "telegram:/profile",
        }

        ev = _make_mock_event(text="hello, how are you?")

        mod = _import_plugin()
        self._patch_plugin_for_status(mod)

        result = mod._pre_gateway_dispatch(event=ev, gateway=gw)

        # The explicit override must survive
        assert session_key in gw._session_model_overrides, (
            "Explicit override was cleared by status intent!"
        )
        override = gw._session_model_overrides[session_key]
        assert override.get("model") == "explicit-model", (
            f"Model changed: {override.get('model')}"
        )
        assert override.get("explicit") is True

    def test_specialist_intent_preserves_explicit_override(self):
        """A specialist-classified message does NOT overwrite an explicit override."""
        session_key = "agent:main:telegram:dm:123"
        gw = _make_mock_gateway(session_key=session_key)
        gw._session_model_overrides[session_key] = {
            "model": "explicit-model",
            "provider": "explicit-provider",
            "profile_name": "myprof",
            "explicit": True,
            "source": "telegram:/profile",
        }

        ev = _make_mock_event(text="review this code for bugs")

        mod = _import_plugin()
        self._patch_plugin_for_specialist(mod, intent="audit", profile="nvidia-auditor")

        result = mod._pre_gateway_dispatch(event=ev, gateway=gw)

        # The explicit override must survive
        assert session_key in gw._session_model_overrides, (
            "Explicit override was cleared by specialist intent!"
        )
        override = gw._session_model_overrides[session_key]
        assert override.get("model") == "explicit-model", (
            f"Model was overwritten: {override.get('model')}"
        )
        assert override.get("explicit") is True

        # Routing header should still be added to the text
        assert result is not None
        assert result.get("action") == "rewrite"
        assert "audit" in result.get("text", "")

    def test_non_explicit_override_is_cleared_by_status(self):
        """A non-explicit auto-routed override IS cleared on status intent."""
        session_key = "agent:main:telegram:dm:123"
        gw = _make_mock_gateway(session_key=session_key)
        # Auto-routed override (no explicit marker)
        gw._session_model_overrides[session_key] = {
            "model": "auto-model",
            "provider": "auto-provider",
            "profile_name": "nvidia-implementer",
            "routing_intent": "implementation",
        }

        ev = _make_mock_event(text="thank you, that's done")

        mod = _import_plugin()
        self._patch_plugin_for_status(mod)

        result = mod._pre_gateway_dispatch(event=ev, gateway=gw)

        # Auto-routed override should be cleared
        assert session_key not in gw._session_model_overrides, (
            "Non-explicit override should be cleared on status intent"
        )

    def test_non_explicit_override_is_overwritten_by_specialist(self):
        """A non-explicit auto-routed override IS overwritten by specialist route."""
        session_key = "agent:main:telegram:dm:123"
        gw = _make_mock_gateway(session_key=session_key)
        # Old auto-routed override from a previous turn
        gw._session_model_overrides[session_key] = {
            "model": "old-model",
            "provider": "old-provider",
            "profile_name": "nvidia-planner",
            "routing_intent": "planning",
        }

        ev = _make_mock_event(text="implement this feature now")

        mod = _import_plugin()
        self._patch_plugin_for_specialist(
            mod, intent="implementation", profile="nvidia-implementer",
        )

        result = mod._pre_gateway_dispatch(event=ev, gateway=gw)

        # Non-explicit override should be overwritten with new specialist
        assert session_key in gw._session_model_overrides, (
            "Non-explicit override missing after specialist route"
        )
        new_override = gw._session_model_overrides[session_key]
        assert new_override.get("model") == "new-specialist", (
            f"Expected specialist model, got {new_override.get('model')}"
        )


# ──────────────────────────────────────────────────────────────────
# Plugin-level: _do_profile_route MUST mark override as explicit so
# the very next status-intent message does not silently clear it.
# Regression test for: /profile <name> followed by /profile status
# reports active_profile=default + override_present=false.
# ──────────────────────────────────────────────────────────────────


class TestPluginDoProfileRouteMarksExplicit:
    """The telegram-router plugin's _do_profile_route must set explicit=True.

    Without this marker, the status-intent branch of _pre_gateway_dispatch
    (which classifies any subsequent non-specialist message — including
    /profile status itself) pops the override before the gateway can read it.
    """

    def test_do_profile_route_sets_explicit_marker(self):
        session_key = "agent:main:telegram:dm:42"
        gw = _make_mock_gateway(session_key=session_key)
        ev = _make_mock_event(text="/profile gpt-implementer")

        mod = _import_plugin()

        # Stub load_profile_model_config so the test doesn't require a real
        # profile config on disk inside the test environment.
        fake_cfg = {
            "model": "gpt-5.5",
            "provider": "openai-codex",
            "base_url": "https://example.test/v1",
            "api_mode": "chat_completions",
            "api_key": "",
            "disabled_toolsets": [],
        }
        with patch.object(
            mod, "load_profile_model_config", return_value=fake_cfg, create=True
        ):
            result = mod._do_profile_route(
                "gpt-implementer", "", ev, gw,
            )

        assert session_key in gw._session_model_overrides
        ov = gw._session_model_overrides[session_key]
        assert ov.get("explicit") is True, (
            f"_do_profile_route override missing explicit=True: {ov!r}"
        )
        assert ov.get("source") == "telegram:/profile", (
            f"_do_profile_route override missing source marker: {ov!r}"
        )
        assert ov.get("profile_name") == "gpt-implementer"
        assert ov.get("model") == "gpt-5.5"

    def test_do_profile_route_explicit_marker_survives_status_intent(self):
        """End-to-end: /profile <name> then /profile status preserves override."""
        session_key = "agent:main:telegram:dm:42"
        gw = _make_mock_gateway(session_key=session_key)

        mod = _import_plugin()
        fake_cfg = {
            "model": "gpt-5.5",
            "provider": "openai-codex",
            "base_url": "https://example.test/v1",
            "api_mode": "chat_completions",
            "api_key": "",
            "disabled_toolsets": [],
        }
        # Step 1: /profile gpt-implementer via _do_profile_route
        with patch.object(
            mod, "load_profile_model_config", return_value=fake_cfg, create=True
        ):
            mod._do_profile_route("gpt-implementer", "", _make_mock_event(), gw)

        assert gw._session_model_overrides[session_key].get("explicit") is True

        # Step 2: /profile status — should be classified as non-specialist,
        # non-approval intent. The explicit marker must protect the override.
        status_event = _make_mock_event(text="/profile status")

        # Patch classifier helpers so the plugin treats this as a status intent.
        with patch.object(mod, "classify_telegram_intent", return_value="status",
                          create=True), \
             patch.object(mod, "load_telegram_orchestrator_policy",
                          return_value={}, create=True), \
             patch.object(mod, "select_profile_for_intent",
                          return_value={"profile": "default",
                                        "requires_specialist": False,
                                        "requires_approval": False},
                          create=True), \
             patch.object(mod, "_is_telegram", return_value=True, create=True):
            mod._pre_gateway_dispatch(event=status_event, gateway=gw)

        # The explicit override must still be present after the status pass.
        assert session_key in gw._session_model_overrides, (
            "explicit /profile override was cleared by status-intent path"
        )
        assert gw._session_model_overrides[session_key].get("model") == "gpt-5.5"


# ──────────────────────────────────────────────────────────────────
# Plugin-level: /prompt <profile> prefix MUST mark override explicit so
# later status/specialist routing cannot clear or overwrite the chosen profile.
# ──────────────────────────────────────────────────────────────────


class TestPluginPromptProfilePrefixMarksExplicit:
    """The /prompt profile-prefix path must preserve explicit user intent."""

    def _apply_prompt_profile_prefix(self, mod, gw, ev):
        fake_cfg = {
            "model": "gpt-5.5",
            "provider": "openai-codex",
            "base_url": "https://example.test/v1",
            "api_mode": "chat_completions",
            "api_key": "",
            "disabled_toolsets": [],
        }
        with patch(
            "gateway.telegram_orchestrator_routing.resolve_profile_name",
            return_value={
                "status": "ok",
                "canonical": "gpt-implementer",
                "available": [],
            },
        ), patch(
            "gateway.telegram_orchestrator_routing.load_profile_model_config",
            return_value=fake_cfg,
        ):
            return mod._t104_handle_prompt_profile_prefix(
                "/prompt gpt-implementer test task", ev, gw,
            )

    def test_prompt_profile_prefix_sets_explicit_marker(self):
        session_key = "agent:main:telegram:dm:42"
        gw = _make_mock_gateway(session_key=session_key)
        ev = _make_mock_event(text="/prompt gpt-implementer test task")

        mod = _import_plugin()
        result = self._apply_prompt_profile_prefix(mod, gw, ev)

        assert result == {"action": "rewrite", "text": "test task"}
        assert session_key in gw._session_model_overrides
        ov = gw._session_model_overrides[session_key]
        assert ov.get("explicit") is True
        assert ov.get("source") == "telegram:/prompt-profile-prefix"
        assert ov.get("profile_name") == "gpt-implementer"
        assert ov.get("model") == "gpt-5.5"
        assert ov.get("provider") == "openai-codex"
        gw._evict_cached_agent.assert_called_once_with(session_key)

    def test_prompt_profile_prefix_explicit_survives_status_intent(self):
        session_key = "agent:main:telegram:dm:42"
        gw = _make_mock_gateway(session_key=session_key)
        mod = _import_plugin()

        self._apply_prompt_profile_prefix(
            mod, gw, _make_mock_event(text="/prompt gpt-implementer test task"),
        )
        assert gw._session_model_overrides[session_key].get("explicit") is True

        status_event = _make_mock_event(text="/profile status")
        with patch.object(mod, "classify_telegram_intent", return_value="status",
                          create=True), \
             patch.object(mod, "load_telegram_orchestrator_policy",
                          return_value={}, create=True), \
             patch.object(mod, "select_profile_for_intent",
                          return_value={"profile": "default",
                                        "requires_specialist": False,
                                        "requires_approval": False},
                          create=True), \
             patch.object(mod, "_is_telegram", return_value=True, create=True):
            mod._pre_gateway_dispatch(event=status_event, gateway=gw)

        assert session_key in gw._session_model_overrides
        ov = gw._session_model_overrides[session_key]
        assert ov.get("explicit") is True
        assert ov.get("source") == "telegram:/prompt-profile-prefix"
        assert ov.get("model") == "gpt-5.5"

    def test_prompt_profile_prefix_explicit_survives_specialist_intent(self):
        session_key = "agent:main:telegram:dm:42"
        gw = _make_mock_gateway(session_key=session_key)
        mod = _import_plugin()

        self._apply_prompt_profile_prefix(
            mod, gw, _make_mock_event(text="/prompt gpt-implementer test task"),
        )
        assert gw._session_model_overrides[session_key].get("explicit") is True

        specialist_event = _make_mock_event(text="review this code for bugs")
        with patch.object(mod, "classify_telegram_intent", return_value="audit",
                          create=True), \
             patch.object(mod, "load_telegram_orchestrator_policy",
                          return_value={}, create=True), \
             patch.object(mod, "select_profile_for_intent",
                          return_value={"profile": "nvidia-auditor",
                                        "requires_specialist": True,
                                        "requires_approval": False},
                          create=True), \
             patch.object(mod, "format_routing_decision",
                          return_value="[routing: audit -> nvidia-auditor]",
                          create=True), \
             patch.object(mod, "load_profile_model_config",
                          return_value={"model": "new-specialist",
                                        "provider": "new-prov"},
                          create=True), \
             patch.object(mod, "_is_telegram", return_value=True, create=True):
            result = mod._pre_gateway_dispatch(event=specialist_event, gateway=gw)

        assert session_key in gw._session_model_overrides
        ov = gw._session_model_overrides[session_key]
        assert ov.get("explicit") is True
        assert ov.get("source") == "telegram:/prompt-profile-prefix"
        assert ov.get("model") == "gpt-5.5"
        assert result is not None
        assert result.get("action") == "rewrite"
        assert "audit" in result.get("text", "")
