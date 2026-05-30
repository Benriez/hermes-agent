"""Tests for CLI /profile command model/provider switch behavior.

Tests verify the fix for /profile <name> applying profile model/provider
overrides to the active session without writing global config.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cli import HermesCLI


def _make_cli():
    """Create a minimal HermesCLI instance for testing slash command handlers."""
    cli = HermesCLI.__new__(HermesCLI)
    cli.config = {}
    cli.console = MagicMock()
    cli.agent = None
    cli.conversation_history = []
    cli.session_id = "session-123"
    cli._pending_input = MagicMock()
    cli.model = "openai/gpt-5.4"
    cli.provider = "openai"
    cli.requested_provider = "openai"
    cli._pending_model_switch_note = None
    return cli


@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    """Set up an isolated profile environment under tmp_path.

    Monkeypatches Path.home() → tmp_path so _get_profiles_root()
    resolves to tmp_path/.hermes/profiles/.  Also sets HERMES_HOME
    so get_hermes_home() / get_active_profile_name() agree.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    default_home = tmp_path / ".hermes"
    default_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(default_home))
    (default_home / "config.yaml").write_text(
        "model:\n  default: base-model\n  provider: base-provider\n"
    )
    return tmp_path


# ────────────────────────────────────────────
# /profile <name> — model/provider switch
# ────────────────────────────────────────────

class TestProfileCommandModelSwitch:

    def test_switch_applies_model_and_provider(self, profile_env, capsys):
        """/profile <name> updates self.model, self.provider, self.requested_provider."""
        prof_dir = profile_env / ".hermes" / "profiles" / "testprof"
        prof_dir.mkdir(parents=True)
        (prof_dir / "config.yaml").write_text(
            "model:\n  default: test-model\n  provider: test-provider\n"
        )

        cli = _make_cli()
        cli._handle_profile_command("/profile testprof")

        assert cli.model == "test-model"
        assert cli.provider == "test-provider"
        assert cli.requested_provider == "test-provider"

        out = capsys.readouterr().out
        assert "testprof" in out

    def test_active_agent_switch_model_called(self, profile_env):
        """When self.agent is active, switch_model() is called with correct args."""
        prof_dir = profile_env / ".hermes" / "profiles" / "testprof"
        prof_dir.mkdir(parents=True)
        (prof_dir / "config.yaml").write_text(
            "model:\n  default: test-model\n  provider: test-provider\n"
        )

        cli = _make_cli()
        cli.agent = MagicMock()
        cli._handle_profile_command("/profile testprof")

        cli.agent.switch_model.assert_called_once_with(
            new_model="test-model",
            new_provider="test-provider",
        )

    def test_invalid_profile_preserves_previous_state(self, profile_env, capsys):
        """Calling /profile with a non-existent profile does not change model/provider."""
        cli = _make_cli()
        initial_model = cli.model
        initial_provider = cli.provider
        initial_requested = cli.requested_provider

        cli._handle_profile_command("/profile missing-profile")

        assert cli.model == initial_model
        assert cli.provider == initial_provider
        assert cli.requested_provider == initial_requested

        out = capsys.readouterr().out
        assert "does not exist" in out

    def test_profile_without_model_config_preserves_previous(self, profile_env, capsys):
        """Profile without model/provider override keeps previous values unchanged."""
        prof_dir = profile_env / ".hermes" / "profiles" / "emptyprof"
        prof_dir.mkdir(parents=True)
        # config.yaml exists but has no model section
        (prof_dir / "config.yaml").write_text("other:\n  key: value\n")

        cli = _make_cli()
        initial_model = cli.model
        initial_provider = cli.provider

        cli._handle_profile_command("/profile emptyprof")

        assert cli.model == initial_model
        assert cli.provider == initial_provider

        out = capsys.readouterr().out.lower()
        assert "no model or provider override" in out

    def test_profile_without_config_file_preserves_previous(self, profile_env, capsys):
        """Profile directory exists but has no config.yaml — previous state preserved."""
        prof_dir = profile_env / ".hermes" / "profiles" / "noconfig"
        prof_dir.mkdir(parents=True)
        # No config.yaml at all

        cli = _make_cli()
        initial_model = cli.model
        initial_provider = cli.provider

        cli._handle_profile_command("/profile noconfig")

        assert cli.model == initial_model
        assert cli.provider == initial_provider

        out = capsys.readouterr().out.lower()
        assert "no model or provider override" in out

    def test_pending_model_switch_note_is_set(self, profile_env):
        """After a successful switch, _pending_model_switch_note is populated."""
        prof_dir = profile_env / ".hermes" / "profiles" / "testprof"
        prof_dir.mkdir(parents=True)
        (prof_dir / "config.yaml").write_text(
            "model:\n  default: test-model\n  provider: test-provider\n"
        )

        cli = _make_cli()
        cli._handle_profile_command("/profile testprof")

        assert cli._pending_model_switch_note is not None
        assert "testprof" in cli._pending_model_switch_note
        assert "test-model" in cli._pending_model_switch_note


# ────────────────────────────────────────────
# /profile  and  /profile status  — unchanged
# ────────────────────────────────────────────

class TestProfileNoArgAndStatus:

    def test_profile_no_arg_shows_info(self, profile_env, capsys):
        """/profile (no argument) shows profile name and home."""
        cli = _make_cli()
        cli._handle_profile_command("/profile")

        out = capsys.readouterr().out
        assert "Profile:" in out
        assert "Home:" in out

    def test_profile_status_shows_extended_info(self, profile_env, capsys):
        """/profile status shows PROFILE_STATUS block with model/provider info."""
        cli = _make_cli()
        cli._handle_profile_command("/profile status")

        out = capsys.readouterr().out
        assert "PROFILE_STATUS" in out
        assert "active_profile:" in out
        assert "effective_model:" in out
        assert "effective_provider:" in out
        assert "api_mode:" in out

    def test_profile_status_shows_override_when_model_differs(self, profile_env, capsys):
        """/profile status detects session override when cli.model != config model."""
        # Write a config that differs from _make_cli's model
        (profile_env / ".hermes" / "config.yaml").write_text(
            "model:\n  default: config-only-model\n  provider: openai\n"
        )

        cli = _make_cli()
        # cli.model is "openai/gpt-5.4", config has "config-only-model"
        cli._handle_profile_command("/profile status")

        out = capsys.readouterr().out
        assert "override_present: true" in out
        assert "override_source: session (/model)" in out

    def test_profile_status_no_override_when_model_matches(self, profile_env, capsys):
        """/profile status shows no override when cli.model matches config."""
        (profile_env / ".hermes" / "config.yaml").write_text(
            "model:\n  default: openai/gpt-5.4\n  provider: openai\n"
        )

        cli = _make_cli()
        cli._handle_profile_command("/profile status")

        out = capsys.readouterr().out
        assert "override_present: false" in out
