import os
import sys
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Ensure we can import tradingagents
sys.path.append(str(Path(__file__).parent.parent))

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
import markdown

app = FastAPI(title="TradingAgents Web UI")

# Mount static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

class AnalyzeRequest(BaseModel):
    ticker: str
    asset_type: str = "stock"
    analysis_date: str
    analysts: List[str]
    llm_provider: str
    backend_url: Optional[str] = None
    shallow_thinker: str
    deep_thinker: str
    trading_mode: str = "Futures (Long/Short)"
    timeframe: str = "Short-term (1-2 Weeks)"
    output_language: str = "English"
    report_length: str = "Full (Detailed analysis)"
    research_depth: int = 1
    api_key: str

@app.get("/")
async def root():
    return FileResponse(str(static_dir / "index.html"))

@app.get("/api/options")
async def get_options():
    return {
        "models": MODEL_OPTIONS
    }

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        # 1. Update config
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = req.llm_provider
        if req.backend_url:
            config["backend_url"] = req.backend_url
        config["quick_think_llm"] = req.shallow_thinker
        config["deep_think_llm"] = req.deep_thinker
        config["trading_mode"] = req.trading_mode
        config["timeframe"] = req.timeframe
        config["output_language"] = req.output_language
        config["report_length"] = req.report_length
        config["max_debate_rounds"] = req.research_depth
        config["max_risk_discuss_rounds"] = req.research_depth
        
        if not req.api_key or not req.api_key.strip():
            raise Exception("API Key is strictly required from the UI. Reading from .env is disabled.")

        # Remove any existing API keys from environment to prevent .env fallback
        for k in list(os.environ.keys()):
            if k.endswith("_API_KEY"):
                del os.environ[k]

        # Force API key from request into environment
        env_var = f"{req.llm_provider.upper()}_API_KEY"
        os.environ[env_var] = req.api_key.strip()

        # 2. Initialize Graph
        ta = TradingAgentsGraph(
            selected_analysts=req.analysts,
            debug=False,
            config=config
        )

        # 3. Run Analysis
        final_state, decision = ta.propagate(
            company_name=req.ticker, 
            trade_date=req.analysis_date,
            asset_type=req.asset_type
        )

        # 4. Format Output
        report_parts = []
        
        # Portfolio Management (Moved to top)
        if final_state.get("final_trade_decision"):
            report_parts.append("## Portfolio Management Decision")
            report_parts.append(str(final_state["final_trade_decision"]))
            
        # Analysts
        analyst_sections = ["market_report", "sentiment_report", "news_report", "fundamentals_report"]
        analyst_titles = ["Market Analysis", "Social Sentiment", "News Analysis", "Fundamentals Analysis"]
        
        has_analyst_report = False
        for sec, title in zip(analyst_sections, analyst_titles):
            if final_state.get(sec):
                if not has_analyst_report:
                    report_parts.append("## Analyst Team Reports")
                    has_analyst_report = True
                report_parts.append(f"### {title}\n{final_state[sec]}")

        # Research Team
        if final_state.get("investment_plan"):
            report_parts.append("## Research Team Decision")
            report_parts.append(str(final_state["investment_plan"]))

        # Trading Team
        if final_state.get("trader_investment_plan"):
            report_parts.append("## Trading Team Plan")
            report_parts.append(str(final_state["trader_investment_plan"]))

        final_markdown = "\n\n".join(report_parts)
        
        # Convert to HTML for easier display, or return raw markdown.
        # Returning raw markdown allows frontend to render it cleanly with marked.js
        
        return {
            "status": "success",
            "decision": decision,
            "report_markdown": final_markdown,
            "raw_state": final_state # Include raw state in case frontend wants it
        }

    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}

