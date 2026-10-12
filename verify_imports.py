"""Run: python verify_imports.py  (same checks as import data_utils; import app)."""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
cache = ROOT / "__pycache__"
if cache.is_dir():
    shutil.rmtree(cache)

sys.path.insert(0, str(ROOT))

APP_IMPORTS = [
    "ASP",
    "TESTPAC_ENERGY_SAVINGS",
    "UNITS_PER_LOT",
    "build_analysis_export",
    "daily_summary",
    "enrich_yield",
    "environmental_yield_impact",
    "explain_daily_yield_variance",
    "financial_impact",
    "load_all_yield",
    "load_weather",
    "operator_day_controlled_analysis",
    "same_day_peer_comparison",
    "weather_correlations",
]

du = importlib.import_module("data_utils")
missing = [n for n in APP_IMPORTS if not hasattr(du, n)]
if missing:
    raise SystemExit(f"data_utils missing exports: {missing}")

import app  # noqa: F401

daily = du.daily_summary(du.enrich_yield(du.load_all_yield(), du.load_weather()))
_, _, env = du.environmental_yield_impact(daily)
assert env["total_scenario_lost_revenue_usd"] > 0

print("OK: import data_utils; import app")
