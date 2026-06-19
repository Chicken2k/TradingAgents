"""Run TradingAgents analysis with pre-configured parameters (non-interactive)."""
import os
import sys

# Remove Hermes paths from sys.path to prevent import conflicts
sys.path = [p for p in sys.path if 'hermes' not in p.lower()]

# === 1. Load .env for API keys ===
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)

# === 2. Set env overrides to skip interactive prompts ===
os.environ["TRADINGAGENTS_LLM_PROVIDER"] = "deepseek"
os.environ["TRADINGAGENTS_QUICK_THINK_LLM"] = "deepseek-v4-flash"
os.environ["TRADINGAGENTS_DEEP_THINK_LLM"] = "deepseek-v4-pro"
os.environ["TRADINGAGENTS_OUTPUT_LANGUAGE"] = "Vietnamese"
os.environ["TRADINGAGENTS_TRADING_MODE"] = "Futures (Long/Short)"
os.environ["TRADINGAGENTS_TIMEFRAME"] = "Short-term (1-2 Weeks)"
os.environ["TRADINGAGENTS_REPORT_LENGTH"] = "Concise (Brief summary)"

# === 3. Bypass all interactive prompts ===
# 3a. Patch get_user_selections to return hardcoded values
from cli.models import AnalystType
from datetime import datetime

def fake_get_user_selections():
    from tradingagents.llm_clients.api_key_env import get_api_key_env
    env_var = get_api_key_env("deepseek")
    key = os.environ.get(env_var) if env_var else None
    if key:
        print(f"[✓] {env_var} found in environment")
    else:
        print(f"[⚠] {env_var} not set — API calls may fail")
    return {
        "ticker": "BTC-USD",
        "asset_type": "crypto",
        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
        "analysts": [AnalystType.MARKET, AnalystType.NEWS],
        "research_depth": 1,
        "llm_provider": "deepseek",
        "backend_url": "https://api.deepseek.com/v1",
        "shallow_thinker": "deepseek-v4-flash",
        "deep_thinker": "deepseek-v4-pro",
        "google_thinking_level": None,
        "openai_reasoning_effort": None,
        "anthropic_effort": None,
        "output_language": "Vietnamese",
        "trading_mode": "Futures (Long/Short)",
        "timeframe": "Short-term (1-2 Weeks)",
        "report_length": "Concise (Brief summary)",
    }

import cli.main
cli.main.get_user_selections = fake_get_user_selections

# 3b. Patch typer.prompt to auto-answer
import typer
_original_prompt = typer.prompt
def _auto_prompt(text, default="", **kwargs):
    """Auto-answer all prompts."""
    if "Display full report" in text:
        return "N"
    if "Save report" in text or "Save path" in text:
        answer = default if default else "Y"
        print(f"[Auto] {text} → '{answer}'")
        return answer
    return _original_prompt(text, default=default, **kwargs)
typer.prompt = _auto_prompt

# Close stdin to prevent terminal access
import io
sys.stdin = io.StringIO()

# Set TERM to a value that prompt_toolkit handles gracefully
os.environ["TERM"] = "dumb"

# === 4. Run ===
print("=" * 60)
print("TradingAgents Analysis for BTC-USD")
print("Provider: DeepSeek (V4 Flash / V4 Pro)")
print("Analysts: Market + News | Depth: Shallow | Report: Concise")
print("=" * 60)

try:
    from cli.main import run_analysis
    run_analysis(checkpoint=False)
except KeyboardInterrupt:
    print("\n[yellow]Analysis interrupted.[/yellow]")
except Exception as e:
    print(f"\n[red]Error: {e}[/red]")
    import traceback
    traceback.print_exc()
