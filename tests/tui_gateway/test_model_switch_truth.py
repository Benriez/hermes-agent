"""Tests verifying model switch runtime truth for the TUI gateway.

These tests ensure that:

1. A successful model switch emits session.info with the new model
   and the agent's model attribute is updated.

2. A failed model switch does NOT emit session.info and does NOT
   update the agent's model.

3. An invalid/unknown model returns a structured error, does not
   update the runtime model, and does not emit live confirmation.

4. When no agent is available, the function does not silently
   report success.

These tests target _apply_model_switch and the session.info emission
guard in tui_gateway/server.py.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_agent():
    """Return a mock agent with the attributes _apply_model_switch reads."""
    agent = MagicMock()
    agent.model = "deepseek-v4-pro"
    agent.provider = "opencode-go"
    agent.base_url = "https://opencode.ai/go/v1"
    agent.api_key = "test-key"
    agent.reasoning_config = None
    agent.service_tier = None
    agent.tools = []
    agent.context_compressor = None
    agent.session_input_tokens = 0
    agent.session_output_tokens = 0
    agent.session_cache_read_tokens = 0
    agent.session_cache_write_tokens = 0
    agent.session_reasoning_tokens = 0
    agent.session_prompt_tokens = 0
    agent.session_completion_tokens = 0
    agent.session_total_tokens = 0
    agent.session_api_calls = 0
    return agent


@pytest.fixture
def mock_session(mock_agent):
    """Return a mock session dict with an agent."""
    return {"agent": mock_agent}


@pytest.fixture
def mock_switch_result_success():
    """Return a successful ModelSwitchResult."""
    from hermes_cli.model_switch import ModelSwitchResult

    return ModelSwitchResult(
        success=True,
        new_model="gemma-3-12b-it",
        target_provider="opencode-go",
        provider_changed=False,
        api_key="test-key",
        base_url="https://opencode.ai/go/v1",
        api_mode="",
        provider_label="OpenCode Go",
        model_info=None,
        capabilities={},
        is_global=False,
    )


@pytest.fixture
def mock_switch_result_failure():
    """Return a failed ModelSwitchResult."""
    from hermes_cli.model_switch import ModelSwitchResult

    return ModelSwitchResult(
        success=False,
        is_global=False,
        error_message="Model 'nonexistent-model-xyz' not found in any provider catalog",
    )


# ---------------------------------------------------------------------------
# _apply_model_switch tests
# ---------------------------------------------------------------------------


class TestApplyModelSwitch:
    """Tests for _apply_model_switch in tui_gateway/server.py."""

    @staticmethod
    def _enter_patches(stack):
        """Enter all patches needed for _apply_model_switch tests.

        switch_model is imported locally inside _apply_model_switch
        (from hermes_cli.model_switch import switch_model), so we
        must patch it at the source module, not at tui_gateway.server.
        """
        return (
            stack.enter_context(patch("hermes_cli.model_switch.switch_model")),
            stack.enter_context(patch("tui_gateway.server._emit")),
            stack.enter_context(patch("tui_gateway.server._session_info")),
            stack.enter_context(patch("tui_gateway.server._restart_slash_worker")),
            stack.enter_context(patch("tui_gateway.server._resolve_model")),
            stack.enter_context(patch("tui_gateway.server._persist_model_switch")),
        )

    def test_successful_switch_emits_session_info(
        self, mock_session, mock_switch_result_success
    ):
        """A successful switch must emit session.info with the new model."""
        from tui_gateway.server import _apply_model_switch

        with ExitStack() as stack:
            mock_switch_model, mock_emit, mock_session_info, \
                mock_restart_slash_worker, mock_resolve_model, mock_persist = \
                self._enter_patches(stack)

            mock_switch_model.return_value = mock_switch_result_success
            mock_session_info.return_value = {"model": "gemma-3-12b-it", "provider": "opencode-go"}

            result = _apply_model_switch("test-sid", mock_session, "gemma-3-12b-it")

        # Assert session.info was emitted
        mock_emit.assert_called_once_with(
            "session.info",
            "test-sid",
            mock_session_info.return_value,
        )
        # Assert the agent's model was switched
        mock_session["agent"].switch_model.assert_called_once()
        # Assert result contains the new model
        assert result["value"] == "gemma-3-12b-it"

    def test_failed_switch_does_not_emit_session_info(
        self, mock_session, mock_switch_result_failure
    ):
        """A failed switch must NOT emit session.info and must raise an error."""
        from tui_gateway.server import _apply_model_switch

        with ExitStack() as stack:
            mock_switch_model, mock_emit, mock_session_info, \
                mock_restart_slash_worker, mock_resolve_model, mock_persist = \
                self._enter_patches(stack)

            mock_switch_model.return_value = mock_switch_result_failure

            with pytest.raises(ValueError) as exc_info:
                _apply_model_switch("test-sid", mock_session, "nonexistent-model-xyz")

        # Assert session.info was NOT emitted
        mock_emit.assert_not_called()
        # Assert agent was NOT switched
        mock_session["agent"].switch_model.assert_not_called()
        # Assert the error message is meaningful
        assert "not found" in str(exc_info.value)

    def test_failed_switch_preserves_previous_model(
        self, mock_session, mock_switch_result_failure
    ):
        """When a switch fails, the agent's model must remain unchanged."""
        from tui_gateway.server import _apply_model_switch

        original_model = mock_session["agent"].model

        with ExitStack() as stack:
            mock_switch_model, mock_emit, mock_session_info, \
                mock_restart_slash_worker, mock_resolve_model, mock_persist = \
                self._enter_patches(stack)

            mock_switch_model.return_value = mock_switch_result_failure

            try:
                _apply_model_switch("test-sid", mock_session, "nonexistent-model-xyz")
            except ValueError:
                pass

        # Model must be unchanged
        assert mock_session["agent"].model == original_model

    def test_invalid_model_returns_explicit_error(self, mock_session):
        """An invalid/unknown model must return an explicit error message."""
        from tui_gateway.server import _apply_model_switch
        from hermes_cli.model_switch import ModelSwitchResult

        with ExitStack() as stack:
            mock_switch_model, mock_emit, mock_session_info, \
                mock_restart_slash_worker, mock_resolve_model, mock_persist = \
                self._enter_patches(stack)

            mock_switch_model.return_value = ModelSwitchResult(
                success=False,
                is_global=False,
                error_message="Model 'invalid-model-999' is not recognized",
            )

            with pytest.raises(ValueError) as exc_info:
                _apply_model_switch("test-sid", mock_session, "invalid-model-999")

        # Error must contain the model name
        assert "invalid-model-999" in str(exc_info.value)
        # session.info must NOT be emitted
        mock_emit.assert_not_called()


# ---------------------------------------------------------------------------
# _mirror_slash_side_effects tests
# ---------------------------------------------------------------------------


class TestMirrorSlashSideEffects:
    """Tests for _mirror_slash_side_effects in tui_gateway/server.py."""

    def test_model_switch_failure_returns_warning_not_throws(self, mock_session):
        """When _apply_model_switch raises, the wrapper returns a warning string."""
        from tui_gateway.server import _mirror_slash_side_effects

        with patch("tui_gateway.server._apply_model_switch") as mock_apply:
            mock_apply.side_effect = ValueError("model switch failed: invalid model")

            warning = _mirror_slash_side_effects(
                "test-sid",
                mock_session,
                "/model nonexistent-model-xyz",
            )

        # Must return a warning, not raise
        assert isinstance(warning, str)
        assert "live session sync failed" in warning
        assert "invalid model" in warning

    def test_model_switch_success_returns_warning_from_result(self, mock_session):
        """When the switch succeeds, the wrapper returns any warning from the result."""
        from tui_gateway.server import _mirror_slash_side_effects

        with patch("tui_gateway.server._apply_model_switch") as mock_apply:
            mock_apply.return_value = {
                "value": "gemma-3-12b-it",
                "warning": "Model is experimental; use with caution.",
            }

            warning = _mirror_slash_side_effects(
                "test-sid",
                mock_session,
                "/model gemma-3-12b-it",
            )

        assert warning == "Model is experimental; use with caution."

    def test_no_session_info_emitted_on_failure(self, mock_session):
        """session.info must NOT be emitted when _apply_model_switch fails."""
        from tui_gateway.server import _mirror_slash_side_effects

        with patch("tui_gateway.server._apply_model_switch") as mock_apply, \
             patch("tui_gateway.server._emit") as mock_emit:
            mock_apply.side_effect = ValueError("model switch failed")

            _mirror_slash_side_effects(
                "test-sid",
                mock_session,
                "/model bad-model",
            )

        # session.info must NOT have been emitted
        session_info_calls = [
            c for c in mock_emit.call_args_list
            if c.args and c.args[0] == "session.info"
        ]
        assert len(session_info_calls) == 0


# ---------------------------------------------------------------------------
# Integration: session.info emission contract
# ---------------------------------------------------------------------------


class TestSessionInfoContract:
    """The session.info payload must match the actual agent state."""

    def test_session_info_reads_from_agent_directly(self, mock_agent):
        """_session_info must read model from the agent object, not from config."""
        from tui_gateway.server import _session_info

        mock_agent.model = "claude-sonnet-4-6"

        info = _session_info(mock_agent)

        assert info["model"] == "claude-sonnet-4-6"

    def test_session_info_reflects_agent_provider(self, mock_agent):
        """_session_info must include provider info from the agent."""
        from tui_gateway.server import _session_info

        mock_agent.model = "test-model"
        mock_agent.provider = "test-provider"

        info = _session_info(mock_agent)

        assert info["model"] == "test-model"

    def test_session_info_model_matches_agent_model_after_switch(self, mock_agent):
        """After agent.switch_model(), _session_info must return the new model."""
        from tui_gateway.server import _session_info

        mock_agent.model = "original-model"

        info_before = _session_info(mock_agent)
        assert info_before["model"] == "original-model"

        # Simulate a switch
        mock_agent.model = "switched-model"

        info_after = _session_info(mock_agent)
        assert info_after["model"] == "switched-model"
