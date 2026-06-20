import functools
import logging
from collections.abc import Mapping
from typing import Any

import yfinance as yf
from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.fundamental_data_tools import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
)
from tradingagents.agents.utils.macro_data_tools import get_macro_indicators
from tradingagents.agents.utils.market_data_validation_tools import get_verified_market_snapshot
from tradingagents.agents.utils.news_data_tools import (
    get_global_news,
    get_insider_transactions,
    get_news,
)
from tradingagents.agents.utils.prediction_markets_tools import get_prediction_markets
from tradingagents.agents.utils.technical_indicators_tools import get_indicators

# Public surface: the data tools are imported here so agents and the graph
# import them from one place, plus the instrument/language helpers defined below.
__all__ = [
    "get_stock_data",
    "get_indicators",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_news",
    "get_global_news",
    "get_insider_transactions",
    "get_macro_indicators",
    "get_prediction_markets",
    "get_verified_market_snapshot",
    "build_instrument_context",
    "resolve_instrument_identity",
    "get_instrument_context_from_state",
    "get_language_instruction",
    "create_msg_delete",
]

logger = logging.getLogger(__name__)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Applied to every agent whose output reaches the saved report —
    analysts, researchers, debaters, research manager, trader, and
    portfolio manager — so a non-English run produces a fully localized
    report rather than a mix of languages.
    """
    from tradingagents.dataflows.config import get_config
    config = get_config()
    
    instructions = []
    
    lang = config.get("output_language", "English")
    if lang.strip().lower() != "english":
        instructions.append(f"Write your entire response in {lang}.")
        
    report_length = config.get("report_length", "Full")
    if "Concise" in report_length:
        instructions.append("Keep your response brief and concise, focusing only on the most critical points. Do not write a long essay.")
        
    if instructions:
        return " " + " ".join(instructions)
    return ""


def _clean_identity_value(value: Any) -> str | None:
    """Return a trimmed string, or None for empty / placeholder-ish values."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"none", "n/a", "nan", "null"}:
        return None
    return cleaned


@functools.lru_cache(maxsize=256)
def resolve_instrument_identity(ticker: str) -> dict:
    """Resolve deterministic identity metadata (company name, sector, …) for a ticker.

    This exists to stop the pipeline from hallucinating a *different* company
    when a chart pattern suggests a different industry than the real one
    (#814): without a ground-truth name, the market analyst would pattern-match
    the price action to a narrative and invent an identity that then cascaded
    through every downstream agent.

    Best-effort by design: if yfinance is unavailable, rate-limited, or doesn't
    recognise the ticker, we return ``{}`` and the caller falls back to
    ticker-only context rather than failing before analysis starts. Cached so
    the lookup happens at most once per ticker per process.

    The symbol is normalized first (e.g. ``XAUUSD`` -> ``GC=F``) so identity
    resolves for the same instrument the price path actually fetches (#983).
    """
    from tradingagents.dataflows.symbol_utils import normalize_symbol

    try:
        info = yf.Ticker(normalize_symbol(ticker)).info or {}
    except Exception as exc:  # noqa: BLE001 — fail open, never block the run
        logger.debug("Could not resolve instrument identity for %s: %s", ticker, exc)
        return {}

    identity: dict[str, str] = {}
    company_name = _clean_identity_value(info.get("longName")) or _clean_identity_value(
        info.get("shortName")
    )
    if company_name:
        identity["company_name"] = company_name
    for source_key, target_key in (
        ("sector", "sector"),
        ("industry", "industry"),
        ("exchange", "exchange"),
        ("quoteType", "quote_type"),
    ):
        value = _clean_identity_value(info.get(source_key))
        if value:
            identity[target_key] = value
    return identity


def build_instrument_context(
    ticker: str,
    asset_type: str = "stock",
    identity: Mapping[str, str] | None = None,
) -> str:
    """Describe the exact instrument so agents preserve identity and ticker.

    When ``identity`` is provided (resolved deterministically via
    :func:`resolve_instrument_identity`), the company name and business
    classification are injected so agents anchor to the real company rather
    than pattern-matching the price chart to a wrong one (#814).
    """
    is_crypto = asset_type == "crypto"
    instrument_label = "asset" if is_crypto else "instrument"
    context = (
        f"The {instrument_label} to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`)."
    )

    details = []
    if identity:
        name = identity.get("company_name") or identity.get("name")
        if name:
            details.append(f"{'Name' if is_crypto else 'Company'}: {name}")
        sector, industry = identity.get("sector"), identity.get("industry")
        if sector and industry:
            details.append(f"Business classification: {sector} / {industry}")
        elif sector:
            details.append(f"Sector: {sector}")
        elif industry:
            details.append(f"Industry: {industry}")
        if identity.get("exchange"):
            details.append(f"Exchange: {identity['exchange']}")

    if details:
        context += (
            f" Resolved identity: {'; '.join(details)}. "
            "Do not substitute a different company or ticker unless a tool "
            "result explicitly disproves this resolved identity."
        )

    if is_crypto:
        context += (
            " Treat it as a crypto asset rather than a company, and do not "
            "assume company fundamentals are available."
        )
    return context


def build_initial_user_message(
    company_name: str,
    trade_date: str,
    trading_mode: str,
    timeframe: str,
) -> str:
    """Seed the graph with explicit trading preferences the LLM cannot ignore."""
    return (
        f"Analyze {company_name} as of {trade_date}. "
        f"Required trading mode: {trading_mode}. "
        f"Required analysis timeframe: {timeframe}. "
        "Every report header and trade idea must use this exact mode and timeframe. "
        "If any default instruction conflicts with this trading mode or timeframe, "
        "ignore the default and follow the user-selected values."
    )


def get_trading_mode_from_state(state: Mapping[str, Any]) -> str:
    """Read trading mode from graph state, falling back to runtime config."""
    mode = state.get("trading_mode")
    if isinstance(mode, str) and mode.strip():
        return mode.strip()
    from tradingagents.dataflows.config import get_config

    return str(get_config().get("trading_mode", "Spot (Long Only)"))


def get_timeframe_from_state(state: Mapping[str, Any]) -> str:
    """Read timeframe from graph state, falling back to runtime config."""
    timeframe = state.get("timeframe")
    if isinstance(timeframe, str) and timeframe.strip():
        return timeframe.strip()
    from tradingagents.dataflows.config import get_config

    return str(get_config().get("timeframe", "Medium-term (1-3 Months)"))


def is_futures_mode(state: Mapping[str, Any]) -> bool:
    """Return True when the user selected a Futures (long/short) trading mode."""
    return "futures" in get_trading_mode_from_state(state).lower()


def get_trading_preferences_prompt(state: Mapping[str, Any]) -> str:
    """Return mandatory trading-mode/timeframe instructions for analyst prompts."""
    trading_mode = get_trading_mode_from_state(state)
    timeframe = get_timeframe_from_state(state)
    mode_label = "Futures Trading" if is_futures_mode(state) else "Spot Trading"
    lines = [
        "",
        "USER TRADING PREFERENCES (mandatory — reflect exactly in the report header and analysis):",
        f"- Timeframe: {timeframe}",
        f"- Mode: {mode_label} (user selected: {trading_mode})",
        f"Tailor indicator selection, holding horizon, and trade ideas to the {timeframe} horizon.",
    ]
    if is_futures_mode(state):
        lines.append(
            "Futures mode: you may recommend SHORT positions when bearish. "
            "Discuss leverage-appropriate entries, stop-loss, and take-profit levels "
            "for both LONG and SHORT scenarios. Do not describe this run as Spot, "
            "do not use a long-only spot-investor frame, and do not write Spot in "
            "the report header."
        )
    else:
        lines.append(
            "Spot mode (long only): do not recommend short selling; use BUY, HOLD, "
            "or SELL (exit long) only."
        )
    return "\n".join(lines)


def get_futures_risk_debate_prompt(state: Mapping[str, Any], role: str) -> str:
    """Return Futures-specific risk-debate instructions for risk analysts."""
    if not is_futures_mode(state):
        return ""

    timeframe = get_timeframe_from_state(state)
    base = [
        "",
        "FUTURES RISK REVIEW (mandatory):",
        f"- Treat the Trader output as a draft for the {timeframe} horizon; the Portfolio Manager will make the final execution plan.",
        "- Evaluate whether LONG, SHORT, or HOLD is justified after considering liquidation risk, leverage, funding/borrow cost if available, open-interest or squeeze risk if mentioned, and ATR/volatility-adjusted stops.",
        "- Explicitly challenge entries that chase price, stops that sit inside normal volatility, and take-profit levels that do not offer a reasonable risk/reward.",
        "- If key futures data such as funding, open interest, or liquidation clusters is unavailable, state that limitation and reason from the available market/news/sentiment evidence instead of inventing numbers.",
    ]
    role_lower = role.lower()
    if "aggressive" in role_lower:
        base.append(
            "- As the aggressive analyst, argue for taking the best asymmetric futures opportunity, but do not ignore liquidation or squeeze risk."
        )
    elif "conservative" in role_lower:
        base.append(
            "- As the conservative analyst, focus on capital preservation: smaller sizing, lower leverage, wider volatility-aware invalidation, or HOLD if the setup is not clean."
        )
    elif "neutral" in role_lower:
        base.append(
            "- As the neutral analyst, reconcile both sides into a balanced futures plan: direction, confidence, risk/reward, and the key condition that would invalidate the trade."
        )
    return "\n".join(base)


def get_instrument_context_from_state(state: Mapping[str, Any]) -> str:
    """Return the instrument context for the current run.

    Prefers the identity-resolved context computed once at run start and
    stored on the state (see ``TradingAgentsGraph.resolve_instrument_context``).
    Falls back to a ticker-only context — with no network lookup — when the
    state was constructed without it (bare programmatic states, tests), so a
    consumer is never forced to make a yfinance call mid-graph.
    """
    context = state.get("instrument_context")
    if not (isinstance(context, str) and context.strip()):
        context = build_instrument_context(
            str(state["company_of_interest"]),
            state.get("asset_type", "stock"),
        )
    
    trading_mode = get_trading_mode_from_state(state)
    timeframe = get_timeframe_from_state(state)
    context += (
        f" The user has selected the {timeframe} timeframe and {trading_mode} trading mode. "
        f"Your analysis must align with this timeframe."
    )
    if is_futures_mode(state):
        context += " Futures mode is active: you may recommend SHORT when bearish."
    else:
        context += " Spot mode is active: long-only; do not recommend short selling."
    return context


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add a context-anchored placeholder.

        The placeholder must not be a bare ``"Continue"``: some
        OpenAI-compatible providers interpret that literally as the user task
        and produce output about the word "continue" instead of analysing the
        instrument (#888). Anchoring it to the resolved instrument context and
        date keeps the next analyst on-task even if the provider treats the
        placeholder as a standalone request.
        """
        messages = state["messages"]
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        instrument_context = get_instrument_context_from_state(state)
        trade_date = state.get("trade_date", "the requested date")
        placeholder = HumanMessage(
            content=(
                f"Proceed with your assigned analysis for this workflow. "
                f"{instrument_context} The analysis date is {trade_date}."
            )
        )
        return {"messages": removal_operations + [placeholder]}

    return delete_messages



