"""Hard input-budget enforcement before provider requests."""

import pytest


def _big_text(tokens: int) -> str:
    return "x" * (tokens * 4)


def test_enforce_request_input_budget_trims_old_history_and_keeps_last_user():
    from agent.context_compressor import enforce_request_input_budget

    messages = [
        {"role": "system", "content": "core policy"},
        {"role": "user", "content": "old user " + _big_text(10_000)},
        {"role": "assistant", "content": "old assistant " + _big_text(10_000)},
        {"role": "tool", "tool_call_id": "call_1", "content": "old tool " + _big_text(10_000)},
        {"role": "user", "content": "TASK-ID: LOCAL-CONTEXT-123\nlatest instruction"},
    ]

    trimmed, result = enforce_request_input_budget(
        messages,
        context_length=32_768,
        tools=None,
        reserved_output_tokens=4_096,
    )

    assert result.trimmed is True
    assert result.input_budget == 27_034  # 32768 - 4096 - max(1024, 5%)
    assert trimmed[0]["content"] == "core policy"
    assert "TASK-ID: LOCAL-CONTEXT-123" in trimmed[-1]["content"]
    assert "[context trimmed: removed older history/tool output to fit model context]" in trimmed[-1]["content"]
    assert result.estimated_tokens <= result.input_budget


def test_enforce_request_input_budget_truncates_oversized_latest_user_but_keeps_task_id():
    from agent.context_compressor import enforce_request_input_budget

    messages = [
        {"role": "system", "content": "core policy"},
        {
            "role": "user",
            "content": "TASK-ID: HUGE-FIRST-WORKER\n" + _big_text(60_000) + "\nacceptance criteria tail",
        },
    ]

    trimmed, result = enforce_request_input_budget(
        messages,
        context_length=32_768,
        tools=None,
        reserved_output_tokens=4_096,
    )

    assert result.trimmed is True
    assert "TASK-ID: HUGE-FIRST-WORKER" in trimmed[-1]["content"]
    assert "acceptance criteria tail" in trimmed[-1]["content"]
    assert "[context trimmed: removed older history/tool output to fit model context]" in trimmed[-1]["content"]
    assert result.estimated_tokens <= result.input_budget


def test_enforce_request_input_budget_fails_fast_when_system_alone_exceeds_budget():
    from agent.context_compressor import PromptContextBudgetExceeded, enforce_request_input_budget

    messages = [
        {"role": "system", "content": _big_text(40_000)},
        {"role": "user", "content": "latest instruction"},
    ]

    with pytest.raises(PromptContextBudgetExceeded, match="Prompt still exceeds model context after truncation"):
        enforce_request_input_budget(
            messages,
            context_length=32_768,
            tools=None,
            reserved_output_tokens=4_096,
        )


def test_default_output_reserve_scales_for_64k_local_model():
    from agent.context_compressor import resolve_context_budget

    budget = resolve_context_budget(context_length=65_536, max_output_tokens=None)

    assert budget.reserved_output_tokens == 8_192
    assert budget.safety_margin == 3_276
    assert budget.input_budget == 54_068
