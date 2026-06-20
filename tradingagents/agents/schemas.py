"""Pydantic schemas used by agents that produce structured output.

The framework's primary artifact is still prose: each agent's natural-language
reasoning is what users read in the saved markdown reports and what the
downstream agents read as context.  Structured output is layered onto the
three decision-making agents (Research Manager, Trader, Portfolio Manager)
so that:

- Their outputs follow consistent section headers across runs and providers
- Each provider's native structured-output mode is used (json_schema for
  OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic)
- Schema field descriptions become the model's output instructions, freeing
  the prompt body to focus on context and the rating-scale guidance
- A render helper turns the parsed Pydantic instance back into the same
  markdown shape the rest of the system already consumes, so display,
  memory log, and saved reports keep working unchanged
"""

from __future__ import annotations

from enum import Enum
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Shared rating types
# ---------------------------------------------------------------------------


class PortfolioRating(str, Enum):
    """5-tier rating used by the Research Manager and Portfolio Manager."""

    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(str, Enum):
    """3-tier transaction direction used by the Trader.

    The Trader's job is to translate the Research Manager's investment plan
    into a concrete transaction proposal: should the desk execute a Buy, a
    Sell, or sit on Hold this round.  Position sizing and the nuanced
    Overweight / Underweight calls happen later at the Portfolio Manager.
    """

    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"
    SHORT = "Short"
    COVER = "Cover"


# ---------------------------------------------------------------------------
# Research Manager
# ---------------------------------------------------------------------------


class ResearchPlan(BaseModel):
    """Structured investment plan produced by the Research Manager.

    Hand-off to the Trader: the recommendation pins the directional view,
    the rationale captures which side of the bull/bear debate carried the
    argument, and the strategic actions translate that into concrete
    instructions the trader can execute against.
    """

    recommendation: PortfolioRating = Field(
        description=(
            "The investment recommendation. Exactly one of Buy / Overweight / "
            "Hold / Underweight / Sell. Reserve Hold for situations where the "
            "evidence on both sides is genuinely balanced; otherwise commit to "
            "the side with the stronger arguments."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments led to the recommendation. "
            "Speak naturally, as if to a teammate."
        ),
    )
    strategic_actions: str = Field(
        description=(
            "Concrete steps for the trader to implement the recommendation, "
            "including position sizing guidance consistent with the rating."
        ),
    )


def render_research_plan(plan: ResearchPlan) -> str:
    """Render a ResearchPlan to markdown for storage and the trader's prompt context."""
    return "\n".join([
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ])


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------


class TraderProposal(BaseModel):
    """Structured transaction proposal produced by the Trader.

    The trader reads the Research Manager's investment plan and the analyst
    reports, then turns them into a concrete transaction: what action to
    take, the reasoning that justifies it, and the practical levels for
    entry, stop-loss, and sizing.
    """

    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell / Short / Cover.",
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and "
            "the research plan. Two to four sentences."
        ),
    )
    entry_price: float | None = Field(
        default=None,
        description="Optional entry price target in the instrument's quote currency.",
    )
    stop_loss: float | None = Field(
        default=None,
        description="Optional stop-loss price in the instrument's quote currency.",
    )
    take_profit: Optional[float] = Field(
        default=None,
        description="Optional take-profit target price in the instrument's quote currency.",
    )
    position_sizing: str | None = Field(
        default=None,
        description="Optional sizing guidance, e.g. '5% of portfolio'.",
    )


def render_trader_proposal(proposal: TraderProposal) -> str:
    """Render a TraderProposal to markdown.

    The trailing ``FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`` line is
    preserved for backward compatibility with the analyst stop-signal text
    and any external code that greps for it.
    """
    parts = [
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
    ]
    if proposal.entry_price is not None:
        parts.extend(["", f"**Entry Price**: {proposal.entry_price}"])
    if proposal.stop_loss is not None:
        parts.extend(["", f"**Stop Loss**: {proposal.stop_loss}"])
    if getattr(proposal, "take_profit", None) is not None:
        parts.extend(["", f"**Take Profit**: {proposal.take_profit}"])
    if proposal.position_sizing:
        parts.extend(["", f"**Position Sizing**: {proposal.position_sizing}"])
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Futures Trader
# ---------------------------------------------------------------------------


class FuturesAction(str, Enum):
    """Transaction direction used by the Trader for Futures."""

    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"


class FuturesTraderBrief(BaseModel):
    """Preliminary futures direction from the Trader for risk-team debate."""

    action: FuturesAction = Field(
        description="The proposed futures direction before risk review. LONG / SHORT / HOLD.",
    )
    market_context: str = Field(
        description="A 1-2 sentence summary of current market momentum in the requested language.",
    )
    reasoning: str = Field(
        description="Why this direction is warranted, anchored in analyst reports and the research plan.",
    )


def render_futures_trader_brief(brief: FuturesTraderBrief) -> str:
    """Render the Trader's preliminary futures proposal (Section III)."""
    from tradingagents.dataflows.config import get_config

    config = get_config()
    lang = config.get("output_language", "English")
    timeframe = config.get("timeframe", "Medium-term (1-3 Months)")
    is_vi = "vietnamese" in lang.lower() or "tiếng việt" in lang.lower()

    if is_vi:
        parts = [
            "**Đề xuất Futures (bản nháp — chờ Risk Team tranh luận)**",
            "",
            f"Select Timeframe: {timeframe}",
            "",
            f"**Hướng đề xuất**: {brief.action.value}",
            f"**Bối cảnh thị trường**: {brief.market_context}",
            f"**Lý do**: {brief.reasoning}",
            "",
            "_Chiến lược thực thi lệnh cuối cùng sẽ do Portfolio Manager quyết định sau khi Risk Team hoàn tất tranh luận._",
            "",
            f"FINAL TRANSACTION PROPOSAL: **{brief.action.value}**",
        ]
    else:
        parts = [
            "**Futures Proposal (draft — pending risk-team debate)**",
            "",
            f"Select Timeframe: {timeframe}",
            "",
            f"**Proposed Direction**: {brief.action.value}",
            f"**Market Context**: {brief.market_context}",
            f"**Reasoning**: {brief.reasoning}",
            "",
            "_Final order execution strategy will be issued by the Portfolio Manager after the risk debate._",
            "",
            f"FINAL TRANSACTION PROPOSAL: **{brief.action.value}**",
        ]
    return "\n".join(parts)


class FuturesTraderProposal(BaseModel):
    """Final futures execution strategy produced by the Portfolio Manager."""

    timeframe: str = Field(
        default="",
        description="Exact user-selected trading timeframe, e.g. 'Short-term (1-2 Weeks)'.",
    )
    action: FuturesAction = Field(
        description="The futures transaction direction. Exactly one of LONG / SHORT / HOLD.",
    )
    market_context: str = Field(
        description="A 1-2 sentence summary of the current market momentum in the requested language.",
    )
    entry_market: str = Field(
        description="Immediate entry price (Market order). E.g., '65200' or 'N/A'. Do not include the explanation text about market momentum/chờ đợi.",
    )
    entry_limit: str = Field(
        description="Safest entry price (Limit order) target. E.g., '64500' or 'N/A'. Do not include the explanation text about bắt râu nến/đợi giá hồi.",
    )
    entry_stop: str = Field(
        description="Breakout entry price (Stop-Market order) target. E.g., '66100' or 'N/A'. Do not include the explanation text about phá vỡ hỗ trợ/kháng cự.",
    )
    entry_dca: str = Field(
        description="DCA zone and split recommendation, e.g. 'Từ 64000 đến 64500. (30% tại 64500, 70% tại 64000)'. Match format: 'Từ [Giá A] đến [Giá B]. (Đề xuất chia % vốn, VD: 30% tại A, 70% tại B)'.",
    )
    tp1: str = Field(
        description="TP1 price target (Limit order). E.g., '67500'. Do not include the chốt 50% vị thế text.",
    )
    tp2: str = Field(
        description="TP2 price target (Limit order). E.g., '69000'. Do not include the chốt 30% vị thế text.",
    )
    tp3: str = Field(
        description="TP3 Trailing Stop level (suggest price or percentage). E.g., 'trailing stop 2%' or '72000'. Do not include the thả trôi 20% text.",
    )
    hard_sl: str = Field(
        description="Mandatory stop loss target(s) (Stop-Market / other stop loss options). You may specify a hard stop loss price and optionally other stop loss options (e.g., alert/soft stop loss) if appropriate. E.g., '63000' or 'Hard SL 63000, Soft SL 63800'. Do not include the chống cháy tài khoản text.",
    )
    confidence: str = Field(
        default="Medium",
        description="Conviction level for this setup. Use exactly High, Medium, or Low.",
    )
    risk_reward: str = Field(
        default="N/A",
        description="Estimated risk/reward for the main plan, e.g. '1:2.1 using entry_limit, hard_sl, and TP1/TP2'.",
    )
    leverage: str = Field(
        default="N/A",
        description="Recommended conservative leverage range and maximum leverage, e.g. '1x-3x, max 5x'.",
    )
    position_sizing: str = Field(
        default="N/A",
        description="Recommended position sizing or capital allocation for this futures idea.",
    )
    invalidation: str = Field(
        default="N/A",
        description="Clear invalidation condition that cancels the setup before or after entry.",
    )

    @staticmethod
    def _first_number(value: str) -> Optional[float]:
        match = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", str(value))
        if not match:
            return None
        return float(match.group(0).replace(",", ""))

    @model_validator(mode="after")
    def validate_directional_levels(self):
        """Catch obvious LONG/SHORT price inversions before rendering."""
        if self.action == FuturesAction.HOLD:
            return self

        entry = self._first_number(self.entry_market) or self._first_number(self.entry_limit)
        hard_sl = self._first_number(self.hard_sl)
        tp1 = self._first_number(self.tp1)
        tp2 = self._first_number(self.tp2)
        if entry is None:
            return self

        if self.action == FuturesAction.LONG:
            if hard_sl is not None and hard_sl >= entry:
                raise ValueError("LONG hard_sl must be below the entry price")
            if tp1 is not None and tp1 <= entry:
                raise ValueError("LONG tp1 must be above the entry price")
            if tp2 is not None and tp2 <= entry:
                raise ValueError("LONG tp2 must be above the entry price")
        elif self.action == FuturesAction.SHORT:
            if hard_sl is not None and hard_sl <= entry:
                raise ValueError("SHORT hard_sl must be above the entry price")
            if tp1 is not None and tp1 >= entry:
                raise ValueError("SHORT tp1 must be below the entry price")
            if tp2 is not None and tp2 >= entry:
                raise ValueError("SHORT tp2 must be below the entry price")

        return self


def render_futures_proposal(proposal: FuturesTraderProposal) -> str:
    """Render a FuturesTraderProposal to markdown, localizing based on configured output language."""
    from tradingagents.dataflows.config import get_config
    config = get_config()
    lang = config.get("output_language", "English")
    timeframe = proposal.timeframe or config.get("timeframe", "Medium-term (1-3 Months)")

    is_vi = "vietnamese" in lang.lower() or "tiếng việt" in lang.lower()

    if is_vi:
        parts = [
            "[CHIẾN LƯỢC THỰC THI LỆNH FUTURES]",
            "",
            f"Select Timeframe: {timeframe}",
            "",
            f"1. HƯỚNG GIAO DỊCH: {proposal.action.value}",
            f"2. BỐI CẢNH THỊ TRƯỜNG: {proposal.market_context}",
            f"3. ĐỘ TIN CẬY: {proposal.confidence}",
            f"4. TỶ LỆ RỦI RO/LỢI NHUẬN ƯỚC TÍNH: {proposal.risk_reward}",
            f"5. ĐÒN BẨY & KHỐI LƯỢNG ĐỀ XUẤT: {proposal.leverage}; {proposal.position_sizing}",
            f"6. ĐIỀU KIỆN VÔ HIỆU KỊCH BẢN: {proposal.invalidation}",
            "7. CÁC LOẠI LỆNH VÀ ĐIỂM VÀO ĐỀ XUẤT:",
            f"   - Lựa chọn 1 - Vào lệnh ngay lập tức (Lệnh Market / Thị trường): {proposal.entry_market}. Chỉ dùng lệnh này nếu đà giá đang cực kỳ mạnh và việc chờ đợi sẽ làm lỡ mất cơ hội.",
            f"   - Lựa chọn 2 - Lệnh An toàn nhất (Lệnh Limit / Chờ giới hạn): {proposal.entry_limit}. Dùng lệnh này để bắt râu nến/đợi giá hồi về điểm đẹp.",
            f"   - Lựa chọn 3 - Lệnh Đánh Breakout (Lệnh Stop-Market / Dừng thị trường): {proposal.entry_stop}. Cài lệnh này nếu giá phá vỡ hỗ trợ/kháng cự quan trọng.",
            f"   - Lựa chọn 4 - Vùng Gom Lệnh DCA (Dải Lệnh Limit): {proposal.entry_dca}.",
            "8. CHIẾN LƯỢC CHỐT LỜI (CÁC LOẠI LỆNH EXIT):",
            f"   - TP1 (Lệnh Limit): {proposal.tp1} - Khuyên chốt 50% vị thế.",
            f"   - TP2 (Lệnh Limit): {proposal.tp2} - Khuyên chốt 30% vị thế.",
            f"   - TP3 (Lệnh Trailing Stop / Dừng theo dõi): {proposal.tp3} - Gợi ý mức để thả trôi 20% vị thế còn lại gồng lời.",
            "9. CẮT LỖ BẮT BUỘC (STOP LOSS):",
            f"   - Lệnh Hard SL (Stop-Market): {proposal.hard_sl} - Lệnh kích hoạt thị trường bắt buộc để chống cháy tài khoản.",
        ]
    else:
        # English template
        parts = [
            "[FUTURES ORDER EXECUTION STRATEGY]",
            "",
            f"Select Timeframe: {timeframe}",
            "",
            f"1. TRANSACTION DIRECTION: {proposal.action.value}",
            f"2. MARKET CONTEXT: {proposal.market_context}",
            f"3. CONFIDENCE: {proposal.confidence}",
            f"4. ESTIMATED RISK/REWARD: {proposal.risk_reward}",
            f"5. LEVERAGE & POSITION SIZING: {proposal.leverage}; {proposal.position_sizing}",
            f"6. INVALIDATION CONDITION: {proposal.invalidation}",
            "7. ORDER TYPES AND PROPOSED ENTRY POINTS:",
            f"   - Option 1 - Immediate Entry (Market Order): {proposal.entry_market}. Only use this order if momentum is extremely strong and waiting will result in a missed opportunity.",
            f"   - Option 2 - Safest Entry (Limit Order): {proposal.entry_limit}. Use this order to catch price wicks or wait for price to pull back to a favorable point.",
            f"   - Option 3 - Breakout Entry (Stop-Market Order): {proposal.entry_stop}. Set this order if price breaks through key support/resistance.",
            f"   - Option 4 - DCA Accumulation Zone (Limit Order Range): {proposal.entry_dca}.",
            "8. TAKE PROFIT STRATEGY (EXIT ORDER TYPES):",
            f"   - TP1 (Limit Order): {proposal.tp1} - Recommend closing 50% of the position.",
            f"   - TP2 (Limit Order): {proposal.tp2} - Recommend closing 30% of the position.",
            f"   - TP3 (Trailing Stop / Follow-up Stop): {proposal.tp3} - Suggest level to let the remaining 20% of the position run to maximize profit.",
            "9. MANDATORY STOP LOSS:",
            f"   - Hard SL Order (Stop-Market): {proposal.hard_sl} - Mandatory market trigger to prevent liquidation.",
        ]

    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value}**",
    ])
    return "\n".join(parts)




# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------


class PortfolioDecision(BaseModel):
    """Structured output produced by the Portfolio Manager.

    The model fills every field as part of its primary LLM call; no separate
    extraction pass is required. Field descriptions double as the model's
    output instructions, so the prompt body only needs to convey context and
    the rating-scale guidance.
    """

    rating: PortfolioRating = Field(
        description=(
            "The final position rating. Exactly one of Buy / Overweight / Hold / "
            "Underweight / Sell, picked based on the analysts' debate."
        ),
    )
    executive_summary: str = Field(
        description=(
            "A concise action plan covering entry strategy, position sizing, "
            "key risk levels, and time horizon. Two to four sentences."
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate. If prior lessons are referenced in the prompt context, "
            "incorporate them; otherwise rely solely on the current analysis."
        ),
    )
    price_target: float | None = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    take_profit: Optional[float] = Field(
        default=None,
        description="Optional take-profit price in the instrument's quote currency.",
    )
    time_horizon: str | None = Field(
        default=None,
        description="Optional recommended holding period, e.g. '3-6 months'.",
    )


def render_pm_decision(decision: PortfolioDecision) -> str:
    """Render a PortfolioDecision back to the markdown shape the rest of the system expects.

    Memory log, CLI display, and saved report files all read this markdown,
    so the rendered output preserves the exact section headers (``**Rating**``,
    ``**Executive Summary**``, ``**Investment Thesis**``) that downstream
    parsers and the report writers already handle.
    """
    parts = [
        f"**Rating**: {decision.rating.value}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
    ]
    if decision.price_target is not None:
        parts.extend(["", f"**Price Target**: {decision.price_target}"])
    if getattr(decision, "take_profit", None) is not None:
        parts.extend(["", f"**Take Profit**: {decision.take_profit}"])
    if decision.time_horizon:
        parts.extend(["", f"**Time Horizon**: {decision.time_horizon}"])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Sentiment Analyst
# ---------------------------------------------------------------------------


class SentimentBand(str, Enum):
    """Discrete sentiment direction produced by the Sentiment Analyst.

    Six tiers keep the signal granular enough to be actionable while remaining
    small enough for every provider to map reliably from its JSON output.
    """

    BULLISH = "Bullish"
    MILDLY_BULLISH = "Mildly Bullish"
    NEUTRAL = "Neutral"
    MIXED = "Mixed"
    MILDLY_BEARISH = "Mildly Bearish"
    BEARISH = "Bearish"


class SentimentReport(BaseModel):
    """Structured sentiment report produced by the Sentiment Analyst.

    Replaces the previous free-form prose output so downstream consumers
    (dashboards, audit logs, PDF renderers, other agents) can read
    ``overall_band`` and ``overall_score`` without maintaining fragile regex
    fallbacks that drift with every model release. ``narrative`` preserves the
    rich source-by-source analysis; ``render_sentiment_report`` prepends a
    deterministic header so the saved report stays human-readable.
    """

    overall_band: SentimentBand = Field(
        description=(
            "Overall sentiment direction. Exactly one of: "
            "Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. "
            "Use Mixed when sources point in clearly different directions. "
            "Use Neutral only when all sources are genuinely silent or non-committal."
        ),
    )
    overall_score: float = Field(
        ge=0.0,
        le=10.0,
        description=(
            "Numeric sentiment intensity on a 0–10 scale. "
            "0 = maximally bearish, 5 = neutral, 10 = maximally bullish. "
            "Guideline for consistency with overall_band: "
            "Bullish ~6.5–10, Mildly Bullish ~5.5–6.4, Neutral/Mixed ~4.5–5.5, "
            "Mildly Bearish ~3.5–4.4, Bearish ~0–3.4. "
            "Only the 0–10 bounds are enforced."
        ),
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description=(
            "Confidence in the assessment based on data quality and sample size. "
            "Use 'low' when one or more sources returned a placeholder or fewer "
            "than 5 data points; 'medium' when data is present but sparse; "
            "'high' when all three sources returned substantive data."
        ),
    )
    narrative: str = Field(
        description=(
            "Full sentiment report covering, in order: "
            "(1) source-by-source breakdown with specific evidence (cite message "
            "counts, ratios, notable posts); "
            "(2) cross-source divergences and alignments; "
            "(3) dominant narrative themes; "
            "(4) catalysts and risks surfaced by the data; "
            "(5) a markdown table summarising key sentiment signals, their "
            "direction, source, and supporting evidence. "
            "Keep it informative and substantive: develop each section thoroughly "
            "with concrete evidence so every point adds new signal for the trader."
        ),
    )


def render_sentiment_report(report: SentimentReport) -> str:
    """Render a SentimentReport to the markdown shape the rest of the system expects.

    The structured header (band + score + confidence) is prepended to the
    narrative so the saved report is both human-readable and machine-parseable
    without regex.
    """
    return "\n".join([
        f"**Overall Sentiment:** **{report.overall_band.value}** "
        f"(Score: {report.overall_score:.1f}/10)",
        f"**Confidence:** {report.confidence.capitalize()}",
        "",
        report.narrative,
    ])
