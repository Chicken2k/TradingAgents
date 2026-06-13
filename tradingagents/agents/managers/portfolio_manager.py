"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back gracefully to free-text generation.

In Futures mode the Portfolio Manager renders the full order-execution
strategy (Section V) after the risk debate, while the Trader only supplies
a preliminary direction (Section III).
"""

from __future__ import annotations

from tradingagents.agents.schemas import (
    FuturesTraderProposal,
    PortfolioDecision,
    render_futures_proposal,
    render_pm_decision,
)
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_timeframe_from_state,
    get_trading_preferences_prompt,
    is_futures_mode,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_portfolio_manager(llm):
    structured_llm_spot = bind_structured(llm, PortfolioDecision, "Portfolio Manager")
    structured_llm_futures = bind_structured(llm, FuturesTraderProposal, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        if is_futures_mode(state):
            past_section = ""
            if past_context:
                past_section = (
                    f"\n- Prior futures execution strategies for this instrument:\n{past_context}\n"
                    "If a previous strategy (e.g. '[CHIẾN LƯỢC THỰC THI LỆNH FUTURES]') is present, "
                    "adapt its levels for the current context rather than inventing from scratch.\n"
                )

            prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and issue the FINAL futures order execution strategy.

{instrument_context}
{get_trading_preferences_prompt(state)}

This is the authoritative output shown under "Portfolio Manager Decision". Incorporate feedback from the risk debate and adjust the Trader's preliminary direction if warranted.

---

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's preliminary futures proposal (draft): **{trader_plan}**
{lessons_line}{past_section}
**Risk Analysts Debate History:**
{history}

---

You MUST fill every execution field: exact timeframe, market/limit/stop-market entry, DCA zone, TP1/TP2/TP3 trailing, hard stop-loss, confidence, estimated risk/reward, recommended leverage, position sizing, and invalidation condition.
Directional price logic is mandatory:
- LONG: hard stop must be below entry; TP levels must be above entry.
- SHORT: hard stop must be above entry; TP levels must be below entry.
- HOLD: use "N/A" for execution prices and explain why no trade is justified.
Ground every level in evidence from the debate. The direction may be LONG, SHORT, or HOLD.{get_language_instruction()}"""

            def render_futures_with_state(proposal: FuturesTraderProposal) -> str:
                if not proposal.timeframe:
                    proposal.timeframe = get_timeframe_from_state(state)
                return render_futures_proposal(proposal)

            final_trade_decision = invoke_structured_or_freetext(
                structured_llm_futures,
                llm,
                prompt,
                render_futures_with_state,
                "Portfolio Manager",
            )
        else:
            prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

            final_trade_decision = invoke_structured_or_freetext(
                structured_llm_spot,
                llm,
                prompt,
                render_pm_decision,
                "Portfolio Manager",
            )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
        }

    return portfolio_manager_node
