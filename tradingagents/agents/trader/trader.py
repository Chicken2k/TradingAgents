"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import (
    TraderProposal,
    render_trader_proposal,
    FuturesTraderProposal,
    render_futures_proposal,
)
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_trader(llm):
    structured_llm_spot = bind_structured(llm, TraderProposal, "Trader")
    structured_llm_futures = bind_structured(llm, FuturesTraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = get_instrument_context_from_state(state)
        investment_plan = state["investment_plan"]
        trading_mode = state.get("trading_mode", "Spot")
        is_futures = "futures" in trading_mode.lower()

        if is_futures:
            # Load past strategy history
            past_context = state.get("past_context", "")
            past_section = ""
            if past_context:
                past_section = (
                    f"\n\nBelow is the past decision/strategy history for {company_name}. "
                    "If a previous futures execution strategy (e.g. '[CHIẾN LƯỢC THỰC THI LỆNH FUTURES]' or similar) is present, "
                    "review it and adapt/update those levels and decisions for the current context. Do not invent a completely "
                    f"new strategy from scratch if you can build upon the prior one:\n{past_context}"
                )

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a futures trading agent analyzing market data to make leverage investment decisions. "
                        "Based on your analysis, provide a specific recommendation to LONG, SHORT, or HOLD. "
                        "Anchor your reasoning in the analysts' reports, the research plan, and past decisions/strategies. "
                        "You MUST explicitly fill in the market entry price, safest limit entry price, breakout stop-market entry price, "
                        "DCA range and split, chốt lời (TP1, TP2, TP3 Trailing), and stop-loss targets (allowing multiple options if appropriate)."
                        + get_language_instruction()
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Based on a comprehensive analysis by a team of analysts, here is an investment "
                        f"plan tailored for {company_name}. {instrument_context} This plan incorporates "
                        f"insights from current technical market trends, macroeconomic indicators, and "
                        f"social media sentiment. Use this plan as a foundation for evaluating your next "
                        f"trading decision.\n\nProposed Investment Plan: {investment_plan}"
                        f"{past_section}\n\n"
                        f"Leverage these insights to make an informed and strategic futures decision, explicitly "
                        f"including directions, market context, entry strategies, take profit levels, and hard/soft stop-loss."
                    ),
                },
            ]
            trader_plan = invoke_structured_or_freetext(
                structured_llm_futures,
                llm,
                messages,
                render_futures_proposal,
                "Trader",
            )
        else:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a trading agent analyzing market data to make investment decisions. "
                        "Based on your analysis, provide a specific recommendation to buy, sell, short, cover, or hold. "
                        "Anchor your reasoning in the analysts' reports and the research plan. "
                        "You MUST explicitly provide an entry price, a stop-loss, and a take-profit target."
                        + get_language_instruction()
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Based on a comprehensive analysis by a team of analysts, here is an investment "
                        f"plan tailored for {company_name}. {instrument_context} This plan incorporates "
                        f"insights from current technical market trends, macroeconomic indicators, and "
                        f"social media sentiment. Use this plan as a foundation for evaluating your next "
                        f"trading decision.\n\nProposed Investment Plan: {investment_plan}\n\n"
                        f"Leverage these insights to make an informed and strategic decision, explicitly "
                        f"including entry price, stop loss, and take profit levels."
                    ),
                },
            ]
            trader_plan = invoke_structured_or_freetext(
                structured_llm_spot,
                llm,
                messages,
                render_trader_proposal,
                "Trader",
            )

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
