"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import (
    TraderProposal,
    render_trader_proposal,
    FuturesTraderBrief,
    render_futures_trader_brief,
)
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    is_futures_mode,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_trader(llm):
    structured_llm_spot = bind_structured(llm, TraderProposal, "Trader")
    structured_llm_futures = bind_structured(llm, FuturesTraderBrief, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = get_instrument_context_from_state(state)
        investment_plan = state["investment_plan"]
        if is_futures_mode(state):
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a futures trading agent preparing a preliminary direction for the risk team. "
                        "Recommend LONG, SHORT, or HOLD with concise market context and reasoning. "
                        "Do NOT specify final entry, take-profit, or stop-loss levels — the Portfolio Manager "
                        "will issue the full execution strategy after the risk debate."
                        + get_language_instruction()
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Based on a comprehensive analysis by a team of analysts, here is an investment "
                        f"plan tailored for {company_name}. {instrument_context} This plan incorporates "
                        f"insights from current technical market trends, macroeconomic indicators, and "
                        f"social media sentiment. Use this plan as a foundation for your preliminary "
                        f"futures direction.\n\nProposed Investment Plan: {investment_plan}\n\n"
                        f"Provide a draft futures direction (LONG/SHORT/HOLD), market context, and reasoning "
                        f"for the risk team to debate."
                    ),
                },
            ]
            trader_plan = invoke_structured_or_freetext(
                structured_llm_futures,
                llm,
                messages,
                render_futures_trader_brief,
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
