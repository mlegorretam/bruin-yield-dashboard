"""BRUIN | OSAT Yield Investigation — interactive management dashboard."""

from __future__ import annotations

import importlib

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data_utils

importlib.reload(data_utils)

from data_utils import (
    ASP,
    TESTPAC_ENERGY_SAVINGS,
    UNITS_PER_LOT,
    build_analysis_export,
    daily_summary,
    enrich_yield,
    environmental_yield_impact,
    explain_daily_yield_variance,
    financial_impact,
    load_all_yield,
    load_weather,
    operator_day_controlled_analysis,
    same_day_peer_comparison,
    weather_correlations,
)

st.set_page_config(
    page_title="BRUIN | OSAT Yield Investigation",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

NAVY = "#0a1628"
NAVY_MID = "#1e3a5f"
ACCENT = "#2d6cdf"
WHITE = "#ffffff"
MUTED = "#94a3b8"

st.markdown(
    f"""
<style>
    .stApp {{ background-color: #f4f7fb; }}
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {NAVY} 0%, {NAVY_MID} 100%);
    }}
    [data-testid="stSidebar"] * {{ color: {WHITE} !important; }}
    .main-header {{
        background: linear-gradient(90deg, {NAVY} 0%, {NAVY_MID} 100%);
        color: white;
        padding: 1.25rem 1.5rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }}
    .main-header h1 {{ margin: 0; font-size: 1.75rem; font-weight: 700; }}
    .main-header p {{ margin: 0.35rem 0 0 0; opacity: 0.9; font-size: 0.95rem; }}
    div[data-testid="stMetric"] {{
        background: {WHITE};
        border-left: 4px solid {ACCENT};
        padding: 0.75rem 1rem;
        border-radius: 6px;
        box-shadow: 0 1px 3px rgba(10,22,40,0.08);
    }}
    .disclaimer {{
        background: #fff8e6;
        border-left: 4px solid #d97706;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        font-size: 0.9rem;
    }}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="Loading Excel data…")
def load_data():
    yield_raw = load_all_yield()
    weather = load_weather()
    yield_df = enrich_yield(yield_raw, weather)
    daily = daily_summary(yield_df)
    operator_stats = operator_day_controlled_analysis(yield_df)
    weather_corr = weather_correlations(daily)
    variance = explain_daily_yield_variance(daily)
    fin_detail, fin_summary = financial_impact(yield_df, operator_stats)
    env_fin_detail, env_benchmarks, env_fin_summary = environmental_yield_impact(daily)
    export_df = build_analysis_export(yield_df, operator_stats)
    return {
        "yield_df": yield_df,
        "daily": daily,
        "operator_stats": operator_stats,
        "weather_corr": weather_corr,
        "variance": variance,
        "fin_detail": fin_detail,
        "fin_summary": fin_summary,
        "env_fin_detail": env_fin_detail,
        "env_benchmarks": env_benchmarks,
        "env_fin_summary": env_fin_summary,
        "export_df": export_df,
        "weather": weather,
    }


def format_compact_number(n: float | int) -> str:
    """Compact display for large counts (e.g. 15,360,000 → 15.36M)."""
    v = float(n)
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 1_000_000:
        return f"{sign}{a / 1_000_000:.2f}M"
    if a >= 10_000:
        return f"{sign}{a / 1_000:.1f}K"
    if a == int(a):
        return f"{sign}{int(a):,}"
    return f"{sign}{a:,.2f}"


def format_compact_currency(n: float | int) -> str:
    """Compact display for USD (e.g. $5,291,730 → $5.29M)."""
    v = float(n)
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 1_000_000:
        return f"{sign}${a / 1_000_000:.2f}M"
    if a >= 1_000:
        return f"{sign}${a / 1_000:.1f}K"
    return f"{sign}${a:,.0f}"


def format_exact_count(n: float | int) -> str:
    v = float(n)
    return f"{int(v):,}" if v == int(v) else f"{v:,.2f}"


def format_exact_currency(n: float | int) -> str:
    return f"${float(n):,.2f}"


def kpi_row(cols, items):
    for col, (label, value, help_text) in zip(cols, items):
        col.metric(label, value, help=help_text)


def filter_yield_df(df: pd.DataFrame, products, operators, day_range) -> pd.DataFrame:
    out = df[df["product"].isin(products)]
    if operators:
        out = out[out["operator"].isin(operators)]
    d0, d1 = day_range
    out = out[(out["day"] >= d0) & (out["day"] <= d1)]
    return out


def main():
    try:
        data = load_data()
    except FileNotFoundError as exc:
        st.error(
            f"Required Excel file not found: {exc}. "
            "Place Apache File.xlsx, Odyssey File.xlsx, and "
            "Solar Intensity and Humidity - UCLA.xlsx in the project folder."
        )
        st.stop()

    yield_df = data["yield_df"]
    daily = data["daily"]
    operator_stats = data["operator_stats"]
    weather_corr = data["weather_corr"]
    variance = data["variance"]
    fin_detail = data["fin_detail"]
    fin_summary = data["fin_summary"]
    env_fin_detail = data["env_fin_detail"]
    env_benchmarks = data["env_benchmarks"]
    env_fin_summary = data["env_fin_summary"]
    export_df = data["export_df"]

    st.markdown(
        """
<div class="main-header">
  <h1>BRUIN | OSAT Yield Investigation</h1>
  <p>TestPAC OSAT yield, environmental, and operator analysis — 32-day window (Day 1–Day 32)</p>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### Navigation")
        section = st.radio(
            "Section",
            [
                "Executive Overview",
                "Yield Analysis",
                "Environmental Analysis",
                "Operator Investigation",
                "Financial Impact",
                "Management Recommendations",
            ],
            label_visibility="collapsed",
        )
        st.markdown("---")
        st.markdown("**Global filters**")
        all_products = sorted(yield_df["product"].unique())
        sel_products = st.multiselect("Product", all_products, default=all_products)
        all_ops = sorted(yield_df["operator"].unique())
        sel_ops = st.multiselect(
            "Operator / tester",
            all_ops,
            default=[],
            placeholder="All operators",
        )
        min_day = int(yield_df["day"].min())
        max_day = int(yield_df["day"].max())
        day_range = st.slider("Day range", min_day, max_day, (min_day, max_day))
        st.markdown("---")
        csv_bytes = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download analysis (CSV)",
            data=csv_bytes,
            file_name="bruin_osat_yield_analysis.csv",
            mime="text/csv",
            use_container_width=True,
        )

    filtered = filter_yield_df(yield_df, sel_products, sel_ops or all_ops, day_range)
    filtered_daily = daily[
        (daily["product"].isin(sel_products))
        & (daily["day"] >= day_range[0])
        & (daily["day"] <= day_range[1])
    ]

    avg_by_product = filtered.groupby("product")["yield_pct"].mean()
    total_lots = len(filtered)
    total_units = total_lots * UNITS_PER_LOT

    # --- Executive Overview ---
    if section == "Executive Overview":
        c1, c2, c3, c4 = st.columns(4)
        apache_avg = avg_by_product.get("Apache", np.nan)
        odyssey_avg = avg_by_product.get("Odyssey", np.nan)
        kpi_row(
            [c1, c2, c3, c4],
            [
                (
                    "Apache avg yield",
                    f"{apache_avg:.3f}%" if pd.notna(apache_avg) else "—",
                    "Mean lot yield (% good units) across filtered Apache lots",
                ),
                (
                    "Odyssey avg yield",
                    f"{odyssey_avg:.3f}%" if pd.notna(odyssey_avg) else "—",
                    "Mean lot yield across filtered Odyssey lots",
                ),
                (
                    "Lots tested",
                    f"{total_lots:,}",
                    f"Each lot = {UNITS_PER_LOT:,} units",
                ),
                (
                    "Units tested",
                    format_compact_number(total_units),
                    f"Exact: {format_exact_count(total_units)} units. Lots × 10,000 units per lot.",
                ),
            ],
        )

        st.markdown("### Financial & TestPAC context")
        fc1, fc2, fc3 = st.columns(3)
        est_loss = fin_summary["total_lost_revenue_usd"]
        fc1.metric(
            "Est. revenue at risk (flagged shortfalls)",
            format_compact_currency(est_loss),
            help=(
                f"Exact: {format_exact_currency(est_loss)}. "
                "Sum of (peer-day expected − actual) × ASP for statistically flagged operators, shortfalls only."
            ),
        )
        fc2.metric(
            "TestPAC claimed energy savings (32 days)",
            format_compact_currency(TESTPAC_ENERGY_SAVINGS),
            help=f"Exact: {format_exact_currency(TESTPAC_ENERGY_SAVINGS)} over 32 days (claim, not verified here).",
        )
        ratio = est_loss / TESTPAC_ENERGY_SAVINGS if TESTPAC_ENERGY_SAVINGS else np.nan
        fc3.metric(
            "Flagged shortfall / TestPAC savings",
            f"{ratio:.1%}" if pd.notna(ratio) else "—",
            help="Not causal; compares two separate estimates",
        )

        fig = go.Figure()
        for product in sel_products:
            sub = filtered_daily[filtered_daily["product"] == product]
            fig.add_trace(
                go.Scatter(
                    x=sub["day"],
                    y=sub["avg_yield"],
                    mode="lines+markers",
                    name=product,
                )
            )
        fig.update_layout(
            title="Average daily yield by product",
            template="plotly_white",
            paper_bgcolor="white",
            plot_bgcolor="white",
            xaxis_title="Day",
            yaxis_title="Yield (%)",
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Data source structure (from Excel inspection)"):
            st.markdown(
                """
- **Apache File.xlsx** — sheet `Apache`: operators in column `Operator`, yields in `Day 1` … `Day 32` (%).
- **Odyssey File.xlsx** — sheet `Odyssey`: same wide layout.
- **Solar Intensity and Humidity - UCLA.xlsx** — sheet `Data`: rows `Solar Intensity` and `Humidity` by day.
- **Tester IDs:** not present as separate fields; **operator names** identify who ran each lot.
- **Calendar dates:** not provided; analysis uses **Day 1–Day 32** indices only.
                """
            )

    # --- Yield Analysis ---
    elif section == "Yield Analysis":
        st.markdown("### Daily yield trend")
        fig_line = px.line(
            filtered_daily,
            x="day",
            y="avg_yield",
            color="product",
            markers=True,
            title="Average daily yield (both products)",
            labels={"avg_yield": "Yield (%)", "day": "Day"},
        )
        fig_line.update_layout(template="plotly_white", height=420)
        st.plotly_chart(fig_line, use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            fig_hist = px.histogram(
                filtered,
                x="yield_pct",
                color="product",
                barmode="overlay",
                nbins=30,
                opacity=0.65,
                title="Yield distribution by product",
                labels={"yield_pct": "Yield (%)"},
            )
            fig_hist.update_layout(template="plotly_white", height=380)
            st.plotly_chart(fig_hist, use_container_width=True)

        with col_b:
            st.markdown("**Summary statistics**")
            st.dataframe(
                filtered.groupby("product")["yield_pct"]
                .agg(["count", "mean", "std", "min", "max"])
                .round(4)
                .rename(columns={"count": "lots"}),
                use_container_width=True,
            )

        st.markdown("### Yield heatmap (operator × day)")
        heat_product = st.selectbox("Product for heatmap", sel_products, key="heat_prod")
        heat_ops = filtered[filtered["product"] == heat_product]["operator"].unique()
        if sel_ops:
            heat_ops = [o for o in heat_ops if o in sel_ops]
        heat_df = filtered[
            (filtered["product"] == heat_product) & (filtered["operator"].isin(heat_ops))
        ]
        if len(heat_df):
            pivot = heat_df.pivot_table(
                index="operator", columns="day", values="yield_pct", aggfunc="mean"
            )
            fig_heat = px.imshow(
                pivot,
                aspect="auto",
                color_continuous_scale="Blues",
                title=f"{heat_product} — yield % by operator and day",
                labels=dict(x="Day", y="Operator", color="Yield %"),
            )
            fig_heat.update_layout(height=max(400, len(pivot) * 18), template="plotly_white")
            st.plotly_chart(fig_heat, use_container_width=True)
        else:
            st.info("No records for heatmap with current filters.")

    # --- Environmental Analysis ---
    elif section == "Environmental Analysis":
        st.markdown(
            '<div class="disclaimer"><strong>Correlation ≠ causation.</strong> '
            "Daily weather and yield move together in observational data; confounders "
            "(equipment, staffing, product mix) are not measured. Do not infer that weather "
            "alone causes yield changes.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")

        env_daily = filtered_daily.dropna(subset=["solar_intensity", "humidity"])
        c1, c2 = st.columns(2)
        for col, xvar, label in [
            (c1, "solar_intensity", "Solar intensity"),
            (c2, "humidity", "Humidity"),
        ]:
            with col:
                fig_sc = px.scatter(
                    env_daily,
                    x=xvar,
                    y="avg_yield",
                    color="product",
                    trendline="ols",
                    title=f"Daily avg yield vs {label.lower()}",
                    labels={xvar: label, "avg_yield": "Avg yield (%)"},
                )
                fig_sc.update_layout(template="plotly_white", height=380)
                st.plotly_chart(fig_sc, use_container_width=True)

        st.markdown("### Correlation coefficients (daily averages)")
        if len(weather_corr):
            show_corr = weather_corr[weather_corr["product"].isin(sel_products)].copy()
            show_corr["pearson_r"] = show_corr["pearson_r"].round(4)
            show_corr["spearman_r"] = show_corr["spearman_r"].round(4)
            show_corr["pearson_p"] = show_corr["pearson_p"].round(4)
            show_corr["spearman_p"] = show_corr["spearman_p"].round(4)
            st.dataframe(show_corr, use_container_width=True, hide_index=True)
        else:
            st.info("Insufficient days for correlation with current filters.")

        st.markdown("### Does weather explain day-to-day yield variation?")
        st.caption(
            "Simple OLS: daily avg yield ~ solar + humidity (exploratory; not causal)."
        )
        if len(variance):
            vshow = variance[variance["product"].isin(sel_products)].copy()
            for col in ["r_squared", "coef_solar", "coef_humidity", "intercept"]:
                vshow[col] = vshow[col].round(4)
            st.dataframe(vshow, use_container_width=True, hide_index=True)
            for _, row in vshow.iterrows():
                st.write(
                    f"**{row['product']}:** weather linear model R² = **{row['r_squared']:.1%}** "
                    f"of daily average yield variation across {int(row['n_days'])} days."
                )

    # --- Operator Investigation ---
    elif section == "Operator Investigation":
        st.markdown(
            '<div class="disclaimer">Statistical flags highlight **unusual** patterns after '
            "subtracting each day's average yield (same product). This supports audit prioritization "
            "**not** accusations of theft or fraud.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")

        op_show = operator_stats[operator_stats["product"].isin(sel_products)].copy()
        if sel_ops:
            op_show = op_show[op_show["operator"].isin(sel_ops)]

        fig_bar = px.bar(
            op_show.sort_values("mean_day_adjusted_residual"),
            x="mean_day_adjusted_residual",
            y="operator",
            color="product",
            orientation="h",
            title="Mean yield vs same-day peers (day-adjusted residual, % points)",
            labels={"mean_day_adjusted_residual": "Avg residual vs day mean (pp)"},
            height=max(450, len(op_show) * 14),
        )
        fig_bar.update_layout(template="plotly_white")
        st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("### Statistical screening (day-controlled)")
        st.caption(
            "One-sample t-test: operator's daily residuals vs 0. Bonferroni adjustment across "
            "all operator×product tests in the full dataset."
        )
        display_ops = op_show[
            [
                "product",
                "operator",
                "n_lots",
                "mean_yield",
                "mean_day_adjusted_residual",
                "t_stat",
                "p_value",
                "p_value_bonferroni",
                "flag_unusual",
            ]
        ].copy()
        for c in ["mean_yield", "mean_day_adjusted_residual", "t_stat", "p_value", "p_value_bonferroni"]:
            display_ops[c] = display_ops[c].round(4)
        st.dataframe(display_ops.sort_values("p_value_bonferroni"), use_container_width=True, hide_index=True)

        flagged = op_show[op_show["flag_unusual"]]
        if len(flagged):
            st.markdown("### Same-day peer comparison (flagged operators)")
            pick = st.selectbox(
                "Flagged operator",
                options=flagged.apply(lambda r: f"{r['operator']} ({r['product']})", axis=1).tolist(),
            )
            op_name, prod = pick.rsplit(" (", 1)
            prod = prod.rstrip(")")
            op_days = filtered[(filtered["operator"] == op_name) & (filtered["product"] == prod)]
            worst_day = op_days.loc[op_days["residual_vs_day"].idxmin(), "day"]
            day_pick = st.number_input("Day to compare", min_value=min_day, max_value=max_day, value=int(worst_day))
            peers = same_day_peer_comparison(yield_df, prod, op_name, int(day_pick))
            st.dataframe(
                peers[["operator", "yield_pct", "day_product_mean", "residual_vs_day"]].round(4),
                use_container_width=True,
                hide_index=True,
            )
            fig_peers = px.bar(
                peers,
                x="operator",
                y="yield_pct",
                color="role",
                title=f"{prod} — Day {day_pick} yields (all operators)",
                labels={"yield_pct": "Yield (%)"},
            )
            fig_peers.add_hline(
                y=peers["day_product_mean"].iloc[0],
                line_dash="dash",
                line_color="gray",
                annotation_text="Day mean",
            )
            fig_peers.update_layout(template="plotly_white", height=360)
            st.plotly_chart(fig_peers, use_container_width=True)
        else:
            st.info("No operators meet Bonferroni significance threshold in the full dataset.")

    # --- Financial Impact ---
    elif section == "Financial Impact":
        st.markdown("### Assumptions (transparent)")
        st.markdown(
            f"""
| Assumption | Value |
|------------|-------|
| Units per lot | {UNITS_PER_LOT:,} |
| Apache ASP | ${ASP['Apache']:,.2f} / good unit |
| Odyssey ASP | ${ASP['Odyssey']:,.2f} / good unit |
| Expected yield (peer benchmark) | Same **product** & **day** average across all operators |
| Who is in scope | Operators with **Bonferroni-significant** day-adjusted residual (full sample) |
| Shortfall definition | Only lots where **actual &lt; peer-day expected** |

**Formula:** `lost_units = (expected_yield% − actual_yield%) / 100 × {UNITS_PER_LOT:,}`  
**Revenue impact:** `lost_units × ASP`
            """
        )

        st.markdown("### Operator-related yield impact")
        m1, m2, m3 = st.columns(3)
        m1.metric("Flagged operator×product pairs", fin_summary["flagged_operator_product_pairs"])
        m2.metric("Affected lots (shortfalls)", fin_summary["affected_lots"])
        op_shortfall = fin_summary["total_lost_revenue_usd"]
        m3.metric(
            "Operator-related shortfall (est.)",
            format_compact_currency(op_shortfall),
            help=f"Exact: {format_exact_currency(op_shortfall)}.",
        )

        if len(fin_detail):
            show_fin = fin_detail.copy()
            for c in ["expected_yield_pct", "actual_yield_pct", "yield_gap_pct", "lost_units", "lost_revenue_usd"]:
                show_fin[c] = show_fin[c].round(2)
            with st.expander("Lot-level operator shortfall detail"):
                st.dataframe(show_fin, use_container_width=True, hide_index=True)
        else:
            st.info("No lot-level shortfalls for flagged operators under these rules.")

        st.markdown("---")
        st.markdown("### Environmental yield impact (scenario-based)")
        st.markdown(
            '<div class="disclaimer"><strong>Scenario estimate — not a proven loss.</strong> '
            "This exercise asks: *if* daily yield on lower-solar days were as high as on "
            "high-solar days (top quartile), how much good-unit revenue might be at risk? "
            "Solar co-varies with unmeasured factors; this is <strong>not</strong> attribution to "
            "TestPAC or proof of causation. Do <strong>not</strong> add this to the operator "
            "estimate — the scenarios overlap.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")

        env_total = env_fin_summary["total_scenario_lost_revenue_usd"]
        e1, e2, e3, e4 = st.columns(4)
        e1.metric(
            "Solar intensity Q3 threshold",
            f"{env_fin_summary['solar_intensity_q75']:.1f}",
            help="Days with solar ≥ this value define the favorable-solar benchmark sample",
        )
        e2.metric(
            "Top-quartile solar days",
            env_fin_summary["n_top_quartile_days"],
            help=f"Days: {', '.join(f'Day {d}' for d in env_fin_summary['top_quartile_solar_days'])}",
        )
        e3.metric(
            "Product-days below benchmark",
            env_fin_summary["product_days_below_benchmark"],
        )
        e4.metric(
            "Environmental scenario shortfall (est.)",
            format_compact_currency(env_total),
            help=f"Exact scenario total: {format_exact_currency(env_total)} (not additive with operator estimate).",
        )

        bench_show = env_benchmarks.copy()
        for c in ["benchmark_yield_pct", "mean_solar_on_benchmark_days"]:
            bench_show[c] = bench_show[c].round(4)
        st.markdown("**Favorable-solar benchmark yields** (mean daily yield on top-quartile solar days)")
        st.dataframe(bench_show, use_container_width=True, hide_index=True)

        lots_day = env_fin_summary["lots_per_product_day"]
        units_lot = env_fin_summary["units_per_lot"]
        st.caption(
            f"Each product-day uses **{lots_day} lots × {units_lot:,} units** "
            f"(= {lots_day * units_lot:,} units) when scaling gaps to volume."
        )

        if len(env_fin_detail):
            env_show = env_fin_detail.copy()
            for c in [
                "benchmark_yield_pct",
                "actual_daily_yield_pct",
                "yield_gap_pct",
                "scenario_lost_units",
                "scenario_lost_revenue_usd",
            ]:
                env_show[c] = env_show[c].round(2)
            with st.expander("Product-day environmental scenario detail"):
                st.dataframe(env_show, use_container_width=True, hide_index=True)

        st.markdown("### Comparison to TestPAC energy savings (shown separately)")
        st.caption(
            "Operator-related and environmental estimates are **not summed**; they may double-count "
            "the same underlying yield variation."
        )
        comp_fig = go.Figure(
            data=[
                go.Bar(
                    x=[
                        "Operator-related shortfall",
                        "Environmental scenario shortfall",
                        "TestPAC energy savings (claim)",
                    ],
                    y=[
                        fin_summary["total_lost_revenue_usd"],
                        env_total,
                        TESTPAC_ENERGY_SAVINGS,
                    ],
                    marker_color=[ACCENT, "#5b8def", NAVY_MID],
                    text=[
                        f"${fin_summary['total_lost_revenue_usd']:,.0f}",
                        f"${env_total:,.0f}",
                        f"${TESTPAC_ENERGY_SAVINGS:,.0f}",
                    ],
                    textposition="outside",
                )
            ]
        )
        comp_fig.update_layout(
            title="32-day period — three separate figures (not additive)",
            yaxis_title="USD",
            template="plotly_white",
            height=430,
        )
        st.plotly_chart(comp_fig, use_container_width=True)

    # --- Management Recommendations ---
    elif section == "Management Recommendations":
        st.markdown("### Evidence summary (computed from uploaded files)")

        findings: list[str] = []
        for product in sorted(yield_df["product"].unique()):
            sub = yield_df[yield_df["product"] == product]
            findings.append(
                f"- **{product}** overall mean yield **{sub['yield_pct'].mean():.3f}%** "
                f"({len(sub):,} operator-day lots)."
            )

        if len(variance):
            for _, row in variance.iterrows():
                findings.append(
                    f"- **{row['product']}** daily yield vs solar/humidity: linear model R² = "
                    f"**{row['r_squared']:.1%}** — weather co-movement is "
                    f"{'material' if row['r_squared'] > 0.25 else 'limited'} for explaining day-level swings."
                )

        if len(weather_corr):
            for _, row in weather_corr.iterrows():
                findings.append(
                    f"- **{row['product']}** / {row['environmental_variable']}: "
                    f"Pearson r = {row['pearson_r']:.3f} (p = {row['pearson_p']:.4f})."
                )

        flagged_ops = operator_stats[operator_stats["flag_unusual"]]
        if len(flagged_ops):
            for _, row in flagged_ops.iterrows():
                direction = "below" if row["mean_day_adjusted_residual"] < 0 else "above"
                findings.append(
                    f"- **Operator flag:** {row['operator']} ({row['product']}) mean "
                    f"{abs(row['mean_day_adjusted_residual']):.3f} pp {direction} same-day peers "
                    f"(Bonferroni p = {row['p_value_bonferroni']:.4g}). *Requires operational review.*"
                )
        else:
            findings.append(
                "- **Operator screening:** no operator×product pair met Bonferroni α = 0.05 "
                "after day adjustment."
            )

        findings.append(
            f"- **Operator-related shortfall (est.):** **${fin_summary['total_lost_revenue_usd']:,.0f}** "
            f"(flagged operators vs same-day peers; not added to environmental scenario)."
        )
        env_total = env_fin_summary["total_scenario_lost_revenue_usd"]
        findings.append(
            f"- **Environmental scenario shortfall (est.):** **${env_total:,.0f}** — daily yields below "
            f"favorable-solar benchmarks (top-quartile solar days; Apache benchmark "
            f"**{env_fin_summary['benchmark_by_product'].get('Apache', float('nan')):.3f}%**, "
            f"Odyssey **{env_fin_summary['benchmark_by_product'].get('Odyssey', float('nan')):.3f}%**)."
        )
        findings.append(
            f"- **TestPAC claimed energy savings:** **${TESTPAC_ENERGY_SAVINGS:,.0f}** over the same 32-day window."
        )

        st.markdown("\n".join(findings))

        st.markdown("### Financial exposure vs. energy savings")
        if env_total > TESTPAC_ENERGY_SAVINGS:
            exposure_msg = (
                f"The **environmental scenario** (**${env_total:,.0f}**) exceeds TestPAC's "
                f"**${TESTPAC_ENERGY_SAVINGS:,.0f}** savings claim on a gross basis — *if* lower yield "
                f"on non-favorable solar days were fully attributable to environment/power (which is "
                f"**not proven** here). The operator-related estimate (**${fin_summary['total_lost_revenue_usd']:,.0f}**) "
                f"does not by itself outweigh the savings claim."
            )
        else:
            exposure_msg = (
                f"The **environmental scenario** (**${env_total:,.0f}**) is **below** TestPAC's "
                f"**${TESTPAC_ENERGY_SAVINGS:,.0f}** savings claim on a gross basis under this benchmark "
                f"method — but causality is unproven and overlap with operator effects is likely."
            )
        st.markdown(
            exposure_msg
            + " These figures must **not** be summed; reconcile with facility logs before any net ROI conclusion."
        )

        st.markdown("### Interpretation")
        st.markdown(
            """
1. **Power / instability** — Not directly measured in these files. If yield dips cluster on days with "
           "extreme humidity or solar swings, prioritize **facility power & HVAC logs** alongside TestPAC rollout timing.
2. **Cooling / humidity** — Use the environmental section correlations as **hypothesis-generating** only; "
           "validate with chamber telemetry and tester environmental alarms.
3. **Operator-specific patterns** — Day-adjusted residuals and same-day peer charts identify **where to look**; "
           "confirm with tester ID logs, lot traceability, and camera/access records before any HR or legal action.
            """
        )

        st.markdown("### Recommended additional data")
        st.markdown(
            """
- Timestamped **tester/equipment IDs** per lot (not only operator names)
- **Actual calendar dates** aligned to TestPAC install and utility events
- **Power quality** (sags, outages) and HVAC setpoints per test floor
- **Lot IDs / WIP traceability** to reconcile unit counts
- Repeat-measure **gauge R&R** to separate measurement noise from true yield loss
            """
        )


if __name__ == "__main__":
    main()
