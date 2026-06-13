"""Tests for trading mode / timeframe propagation."""

import pytest

from tradingagents.agents.utils.agent_utils import (
    build_initial_user_message,
    get_futures_risk_debate_prompt,
    get_trading_preferences_prompt,
    is_futures_mode,
)
from tradingagents.dataflows import config as dataflows_config
from tradingagents.graph.propagation import Propagator


@pytest.mark.unit
def test_trading_preferences_prompt_mentions_futures():
    state = {
        "trading_mode": "Futures (Long/Short)",
        "timeframe": "Short-term (1-2 Weeks)",
    }
    prompt = get_trading_preferences_prompt(state)
    assert "Futures Trading" in prompt
    assert "Short-term (1-2 Weeks)" in prompt
    assert "SHORT" in prompt


@pytest.mark.unit
def test_futures_risk_debate_prompt_mentions_leverage_and_liquidation():
    state = {
        "trading_mode": "Futures (Long/Short)",
        "timeframe": "Short-term (1-2 Weeks)",
    }
    prompt = get_futures_risk_debate_prompt(state, "conservative")
    assert "liquidation risk" in prompt
    assert "leverage" in prompt
    assert "risk/reward" in prompt
    assert "Short-term (1-2 Weeks)" in prompt


@pytest.mark.unit
def test_initial_user_message_includes_futures_selection():
    msg = build_initial_user_message(
        "BTC-USD",
        "2026-06-08",
        "Futures (Long/Short)",
        "Short-term (1-2 Weeks)",
    )
    assert "Futures (Long/Short)" in msg
    assert "Short-term (1-2 Weeks)" in msg


@pytest.mark.unit
def test_is_futures_mode_falls_back_to_runtime_config(monkeypatch):
    monkeypatch.setattr(
        dataflows_config,
        "get_config",
        lambda: {"trading_mode": "Futures (Long/Short)"},
    )
    assert is_futures_mode({}) is True


@pytest.mark.unit
def test_create_initial_state_carries_trading_selections():
    state = Propagator().create_initial_state(
        "BTC-USD",
        "2026-06-08",
        asset_type="crypto",
        trading_mode="Futures (Long/Short)",
        timeframe="Short-term (1-2 Weeks)",
    )
    assert state["trading_mode"] == "Futures (Long/Short)"
    assert state["timeframe"] == "Short-term (1-2 Weeks)"


@pytest.mark.unit
def test_trading_preferences_prompt_mentions_spot():
    state = {
        "trading_mode": "Spot (Long Only)",
        "timeframe": "Medium-term (1-3 Months)",
    }
    prompt = get_trading_preferences_prompt(state)
    assert "Spot Trading" in prompt
    assert "long only" in prompt.lower()
    assert not is_futures_mode(state)
