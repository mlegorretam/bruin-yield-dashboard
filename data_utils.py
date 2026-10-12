"""Load OSAT yield and environmental data from project Excel files."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent

APACHE_FILE = ROOT / "Apache File.xlsx"
ODYSSEY_FILE = ROOT / "Odyssey File.xlsx"
WEATHER_FILE = ROOT / "Solar Intensity and Humidity - UCLA.xlsx"

UNITS_PER_LOT = 10_000
LOTS_PER_PRODUCT_DAY = 24
ASP = {"Apache": 175.0, "Odyssey": 145.0}
TESTPAC_ENERGY_SAVINGS = 1_250_000.0


def _parse_day_label(label: object) -> int | None:
    if label is None or (isinstance(label, float) and np.isnan(label)):
        return None
    text = str(label).strip()
    match = re.match(r"Day\s*(\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _load_product_yield(path: Path, product: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing data file: {path.name}")

    raw = pd.read_excel(path, sheet_name=0, header=None)
    header_row = None
    for idx in range(min(10, len(raw))):
        row = raw.iloc[idx]
        if row.astype(str).str.contains("Operator", case=False, na=False).any():
            header_row = idx
            break
    if header_row is None:
        raise ValueError(f"Could not locate Operator header row in {path.name}")

    headers = raw.iloc[header_row].tolist()
    data = raw.iloc[header_row + 1 :].copy()
    data.columns = range(len(headers))

    operator_col = None
    day_cols: list[tuple[int, int]] = []
    for col_idx, header in enumerate(headers):
        if str(header).strip().lower() == "operator":
            operator_col = col_idx
        day_num = _parse_day_label(header)
        if day_num is not None:
            day_cols.append((col_idx, day_num))

    if operator_col is None or not day_cols:
        raise ValueError(f"Unexpected layout in {path.name}")

    records: list[dict] = []
    for _, row in data.iterrows():
        operator = row.iloc[operator_col]
        if pd.isna(operator) or str(operator).strip().lower() == "operator":
            continue
        operator = str(operator).strip()
        for col_idx, day_num in day_cols:
            val = row.iloc[col_idx]
            if pd.isna(val):
                continue
            try:
                yield_pct = float(val)
            except (TypeError, ValueError):
                continue
            records.append(
                {
                    "product": product,
                    "operator": operator,
                    "day": day_num,
                    "day_label": f"Day {day_num}",
                    "yield_pct": yield_pct,
                }
            )

    return pd.DataFrame(records)


def load_weather(path: Path | None = None) -> pd.DataFrame:
    path = path or WEATHER_FILE
    if not path.exists():
        raise FileNotFoundError(f"Missing data file: {path.name}")

    raw = pd.read_excel(path, sheet_name=0, header=None)
    header_row = None
    for idx in range(min(10, len(raw))):
        row = raw.iloc[idx]
        if any(_parse_day_label(v) is not None for v in row):
            header_row = idx
            break
    if header_row is None:
        raise ValueError("Could not locate day columns in weather file")

    headers = raw.iloc[header_row].tolist()
    metric_col = 2
    rows: list[dict] = []
    for idx in range(header_row + 1, len(raw)):
        metric = raw.iloc[idx, metric_col]
        if pd.isna(metric):
            continue
        metric_name = str(metric).strip()
        for col_idx, header in enumerate(headers):
            day_num = _parse_day_label(header)
            if day_num is None:
                continue
            val = raw.iloc[idx, col_idx]
            if pd.isna(val):
                continue
            try:
                numeric = float(val)
            except (TypeError, ValueError):
                continue
            rows.append({"day": day_num, "metric": metric_name, "value": numeric})

    wide = (
        pd.DataFrame(rows)
        .pivot_table(index="day", columns="metric", values="value", aggfunc="first")
        .reset_index()
    )
    wide.columns.name = None
    rename = {}
    for col in wide.columns:
        lower = str(col).lower()
        if "solar" in lower:
            rename[col] = "solar_intensity"
        elif "humid" in lower:
            rename[col] = "humidity"
    wide = wide.rename(columns=rename)
    return wide.sort_values("day").reset_index(drop=True)


def load_all_yield() -> pd.DataFrame:
    apache = _load_product_yield(APACHE_FILE, "Apache")
    odyssey = _load_product_yield(ODYSSEY_FILE, "Odyssey")
    return pd.concat([apache, odyssey], ignore_index=True)


def enrich_yield(df: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["day_product_mean"] = out.groupby(["product", "day"])["yield_pct"].transform("mean")
    out["residual_vs_day"] = out["yield_pct"] - out["day_product_mean"]
    out = out.merge(weather, on="day", how="left")
    out["units"] = UNITS_PER_LOT
    out["good_units"] = out["yield_pct"] / 100.0 * UNITS_PER_LOT
    out["asp"] = out["product"].map(ASP)
    out["good_unit_value"] = out["good_units"] * out["asp"]
    return out


def daily_summary(yield_df: pd.DataFrame) -> pd.DataFrame:
    return (
        yield_df.groupby(["product", "day"], as_index=False)
        .agg(
            avg_yield=("yield_pct", "mean"),
            lot_count=("yield_pct", "count"),
            solar_intensity=("solar_intensity", "first"),
            humidity=("humidity", "first"),
        )
        .sort_values(["product", "day"])
    )


def operator_day_controlled_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """One-sample t-tests of day-adjusted residuals by operator (per product)."""
    results: list[dict] = []
    for (product, operator), grp in df.groupby(["product", "operator"]):
        residuals = grp["residual_vs_day"].dropna().values
        n = len(residuals)
        if n < 2:
            t_stat = np.nan
            p_val = np.nan
        else:
            t_stat, p_val = stats.ttest_1samp(residuals, 0.0, nan_policy="omit")
        results.append(
            {
                "product": product,
                "operator": operator,
                "n_lots": n,
                "mean_yield": grp["yield_pct"].mean(),
                "mean_day_adjusted_residual": np.mean(residuals) if n else np.nan,
                "residual_std": np.std(residuals, ddof=1) if n > 1 else np.nan,
                "t_stat": t_stat,
                "p_value": p_val,
            }
        )
    out = pd.DataFrame(results)
    m = out["p_value"].notna().sum()
    out["p_value_bonferroni"] = np.minimum(out["p_value"] * m, 1.0) if m else np.nan
    out["flag_unusual"] = out["p_value_bonferroni"] < 0.05
    return out.sort_values(["product", "mean_day_adjusted_residual"])


def same_day_peer_comparison(
    df: pd.DataFrame, product: str, operator: str, day: int
) -> pd.DataFrame:
    subset = df[(df["product"] == product) & (df["day"] == day)].copy()
    subset["role"] = np.where(subset["operator"] == operator, operator, "Peers (same day)")
    return subset.sort_values("yield_pct")


def weather_correlations(daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for product in daily["product"].unique():
        sub = daily[daily["product"] == product].dropna(
            subset=["avg_yield", "solar_intensity", "humidity"]
        )
        if len(sub) < 3:
            continue
        for env, col in [("Solar Intensity", "solar_intensity"), ("Humidity", "humidity")]:
            r_pearson, p_pearson = stats.pearsonr(sub["avg_yield"], sub[col])
            r_spearman, p_spearman = stats.spearmanr(sub["avg_yield"], sub[col])
            rows.append(
                {
                    "product": product,
                    "environmental_variable": env,
                    "pearson_r": r_pearson,
                    "pearson_p": p_pearson,
                    "spearman_r": r_spearman,
                    "spearman_p": p_spearman,
                    "n_days": len(sub),
                }
            )
    return pd.DataFrame(rows)


def explain_daily_yield_variance(daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for product in daily["product"].unique():
        sub = daily[daily["product"] == product].dropna(
            subset=["avg_yield", "solar_intensity", "humidity"]
        )
        if len(sub) < 4:
            continue
        y = sub["avg_yield"].values
        X = np.column_stack(
            [np.ones(len(sub)), sub["solar_intensity"].values, sub["humidity"].values]
        )
        coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        y_hat = X @ coef
        ss_res = np.sum((y - y_hat) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
        rows.append(
            {
                "product": product,
                "intercept": coef[0],
                "coef_solar": coef[1],
                "coef_humidity": coef[2],
                "r_squared": r2,
                "n_days": len(sub),
            }
        )
    return pd.DataFrame(rows)


def financial_impact(df: pd.DataFrame, operator_flags: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    flagged = set(
        zip(
            operator_flags.loc[operator_flags["flag_unusual"], "product"],
            operator_flags.loc[operator_flags["flag_unusual"], "operator"],
        )
    )
    rows: list[dict] = []
    for _, row in df.iterrows():
        key = (row["product"], row["operator"])
        if key not in flagged:
            continue
        expected = row["day_product_mean"]
        actual = row["yield_pct"]
        if actual >= expected:
            continue
        yield_gap_pct = expected - actual
        lost_units = yield_gap_pct / 100.0 * UNITS_PER_LOT
        lost_revenue = lost_units * row["asp"]
        rows.append(
            {
                "product": row["product"],
                "operator": row["operator"],
                "day": row["day"],
                "expected_yield_pct": expected,
                "actual_yield_pct": actual,
                "yield_gap_pct": yield_gap_pct,
                "lost_units": lost_units,
                "asp": row["asp"],
                "lost_revenue_usd": lost_revenue,
            }
        )
    detail = pd.DataFrame(rows)
    summary = {
        "flagged_operator_product_pairs": len(flagged),
        "affected_lots": len(detail),
        "total_lost_units": detail["lost_units"].sum() if len(detail) else 0.0,
        "total_lost_revenue_usd": detail["lost_revenue_usd"].sum() if len(detail) else 0.0,
    }
    return detail, summary


def environmental_yield_impact(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Scenario: benchmark yield = mean daily yield on top-quartile solar-intensity days (per product).
    Compare each product-day average to that benchmark; scale shortfalls to all lots that day.
    """
    solar_by_day = daily[["day", "solar_intensity"]].drop_duplicates("day")
    solar_q75 = float(solar_by_day["solar_intensity"].quantile(0.75))
    top_solar_days = set(
        solar_by_day.loc[solar_by_day["solar_intensity"] >= solar_q75, "day"].astype(int)
    )

    benchmark_rows: list[dict] = []
    benchmark_by_product: dict[str, float] = {}
    for product in sorted(daily["product"].unique()):
        sub = daily[daily["product"] == product]
        fav = sub[sub["day"].isin(top_solar_days)]
        benchmark = float(fav["avg_yield"].mean()) if len(fav) else np.nan
        benchmark_by_product[product] = benchmark
        benchmark_rows.append(
            {
                "product": product,
                "benchmark_yield_pct": benchmark,
                "benchmark_days_used": len(fav),
                "mean_solar_on_benchmark_days": fav["solar_intensity"].mean() if len(fav) else np.nan,
            }
        )
    benchmarks = pd.DataFrame(benchmark_rows)

    detail_rows: list[dict] = []
    for _, row in daily.iterrows():
        product = row["product"]
        benchmark = benchmark_by_product.get(product, np.nan)
        if pd.isna(benchmark):
            continue
        actual = float(row["avg_yield"])
        if actual >= benchmark:
            continue
        yield_gap_pct = benchmark - actual
        lot_count = (
            int(row["lot_count"])
            if "lot_count" in row.index and pd.notna(row["lot_count"])
            else LOTS_PER_PRODUCT_DAY
        )
        units_at_risk = lot_count * UNITS_PER_LOT
        lost_units = yield_gap_pct / 100.0 * units_at_risk
        asp = ASP[product]
        lost_revenue = lost_units * asp
        detail_rows.append(
            {
                "product": product,
                "day": int(row["day"]),
                "solar_intensity": row["solar_intensity"],
                "top_quartile_solar_day": int(row["day"]) in top_solar_days,
                "benchmark_yield_pct": benchmark,
                "actual_daily_yield_pct": actual,
                "yield_gap_pct": yield_gap_pct,
                "lots": lot_count,
                "units_at_risk": units_at_risk,
                "asp": asp,
                "scenario_lost_units": lost_units,
                "scenario_lost_revenue_usd": lost_revenue,
            }
        )

    detail = pd.DataFrame(detail_rows)
    by_product = (
        detail.groupby("product", as_index=False)["scenario_lost_revenue_usd"].sum()
        if len(detail)
        else pd.DataFrame(columns=["product", "scenario_lost_revenue_usd"])
    )

    summary = {
        "solar_intensity_q75": solar_q75,
        "top_quartile_solar_days": sorted(top_solar_days),
        "n_top_quartile_days": len(top_solar_days),
        "benchmark_by_product": benchmark_by_product,
        "product_days_below_benchmark": len(detail),
        "total_scenario_lost_units": detail["scenario_lost_units"].sum() if len(detail) else 0.0,
        "total_scenario_lost_revenue_usd": detail["scenario_lost_revenue_usd"].sum()
        if len(detail)
        else 0.0,
        "by_product_revenue": by_product.set_index("product")["scenario_lost_revenue_usd"].to_dict()
        if len(by_product)
        else {},
        "lots_per_product_day": LOTS_PER_PRODUCT_DAY,
        "units_per_lot": UNITS_PER_LOT,
    }
    return detail, benchmarks, summary


def build_analysis_export(
    yield_df: pd.DataFrame,
    operator_stats: pd.DataFrame,
) -> pd.DataFrame:
    base = yield_df[
        [
            "product",
            "operator",
            "day",
            "yield_pct",
            "day_product_mean",
            "residual_vs_day",
            "solar_intensity",
            "humidity",
            "good_units",
            "good_unit_value",
        ]
    ].copy()
    return base.merge(
        operator_stats[
            [
                "product",
                "operator",
                "mean_day_adjusted_residual",
                "p_value_bonferroni",
                "flag_unusual",
            ]
        ],
        on=["product", "operator"],
        how="left",
    )
