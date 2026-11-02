"""Settlement and budget analysis for two virtual PPAs (solar and wind) in Germany.

Run after downloading the data:
    python src/portfolio_analytics.py
To test the code with made up data:
    python src/portfolio_analytics.py --demo
"""

import argparse
from pathlib import Path

import duckdb
import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "opsd_germany_hourly.csv"
OUT = ROOT / "outputs"
CHARTS = OUT / "charts"

HISTORY_YEAR = 2019
ANALYSIS_YEAR = 2020

# Hypothetical plants and contract prices
PROJECTS = {
    "Solar VPPA": {"tech": "solar", "capacity_mw": 100, "strike_eur_mwh": 45.0},
    "Wind VPPA": {"tech": "wind_onshore", "capacity_mw": 150, "strike_eur_mwh": 50.0},
}
INVOICE_TOLERANCE = 0.01  # flag invoice lines that differ by more than 1%

# Brand colors (same as the dashboard): amber for solar, green for wind
COLORS = {"Solar VPPA": "#e9a23b", "Wind VPPA": "#2e7d6a"}
TEXT = {"Solar VPPA": "#b5701a", "Wind VPPA": "#2e7d6a"}  # darker amber for text on a light background
BRAND = "#13302b"
SHORT = {"Solar VPPA": "Solar", "Wind VPPA": "Wind"}
INK, INK_2, MUTED, GRID, SURFACE = "#1b2a27", "#4a5a56", "#8a9692", "#ebe7dc", "#fcfbf8"
SOURCE = "Source: Open Power System Data (2020-10-06), DE-LU day-ahead prices. Contracts are hypothetical."


# data
def make_demo_data() -> pd.DataFrame:
    """Made up hourly data with the same columns as OPSD, only for testing."""
    rng = np.random.default_rng(42)
    ts = pd.date_range("2019-01-01", "2020-09-30 23:00", freq="h", tz="UTC")
    hour, doy = ts.hour.values, ts.dayofyear.values
    season = 0.5 + 0.5 * np.cos((doy - 172) / 365 * 2 * np.pi)
    solar = np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None) * (0.25 + 0.5 * season)
    solar *= rng.uniform(0.4, 1.0, len(ts))
    wind = np.clip(0.3 - 0.12 * season + rng.normal(0, 0.12, len(ts)), 0.01, 0.95)
    price = 40 + 10 * np.sin((hour - 3) / 24 * 2 * np.pi) - 15 * solar + rng.normal(0, 8, len(ts))
    price[ts.year == 2020] -= 8
    return pd.DataFrame(
        {
            "utc_timestamp": ts,
            "DE_LU_price_day_ahead": price,
            "DE_solar_profile": np.where(ts.year == 2020, np.nan, solar),
            "DE_wind_onshore_profile": np.where(ts.year == 2020, np.nan, wind),
            "DE_solar_capacity": np.where(ts.year == 2020, np.nan, 49000.0),
            "DE_solar_generation_actual": solar * 49000,
            "DE_wind_onshore_capacity": np.where(ts.year == 2020, np.nan, 53000.0),
            "DE_wind_onshore_generation_actual": wind * 53000,
        }
    )


def load_data(demo: bool) -> pd.DataFrame:
    if demo:
        df = make_demo_data()
    else:
        if not DATA.exists():
            raise SystemExit("Data file not found. Run: python src/download_data.py")
        df = pd.read_csv(DATA, parse_dates=["utc_timestamp"])
    df["utc_timestamp"] = pd.to_datetime(df["utc_timestamp"], utc=True)
    df["local_time"] = df["utc_timestamp"].dt.tz_convert("Europe/Berlin")
    # Capacity factor = actual national generation / installed capacity.
    # The OPSD profile columns stop before 2020, so the same formula is used for
    # both years. Capacity is carried forward when the latest value is missing.
    for tech in ("solar", "wind_onshore"):
        gen, cap, prof = (f"DE_{tech}_generation_actual", f"DE_{tech}_capacity", f"DE_{tech}_profile")
        if gen in df and cap in df and df[cap].notna().any():
            cf = df[gen] / df[cap].ffill()
        else:
            cf = df[prof]
        df[prof] = cf.interpolate(limit=3).clip(0, 1)
    df = df.rename(columns={"DE_LU_price_day_ahead": "price_eur_mwh"})
    df = df.dropna(subset=["price_eur_mwh"])
    df["year"] = df["local_time"].dt.year
    df["month"] = df["local_time"].dt.month
    df["hour"] = df["local_time"].dt.hour
    # Data check: share of hours with a capacity factor, by year
    for tech in ("solar", "wind_onshore"):
        cov = df.groupby("year")[f"DE_{tech}_profile"].apply(lambda x: x.notna().mean())
        print(f"Hours with {tech} data: " + ", ".join(f"{y}: {v:.0%}" for y, v in cov.items()))
        if (cov < 0.9).any():
            print(f"WARNING: {tech} data is incomplete in some years, check the results")
    return df


def project_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Hourly generation and settlement for each contract."""
    rows = []
    for name, p in PROJECTS.items():
        g = df[["local_time", "year", "month", "hour", "price_eur_mwh"]].copy()
        g["project"] = name
        cf = df[f"DE_{p['tech']}_profile"].clip(0, 1).fillna(0)
        g["capacity_factor"] = cf
        g["generation_mwh"] = cf * p["capacity_mw"]
        g["strike_eur_mwh"] = p["strike_eur_mwh"]
        # Positive settlement = buyer receives money (market above strike)
        g["settlement_eur"] = (g["price_eur_mwh"] - g["strike_eur_mwh"]) * g["generation_mwh"]
        rows.append(g)
    return pd.concat(rows, ignore_index=True)


# forecast
def budget_forecast(hourly: pd.DataFrame, months: list[int]) -> pd.DataFrame:
    """Monthly budget for 2020 built only with 2019 data."""
    hist = hourly[hourly["year"] == HISTORY_YEAR]
    out = []
    for name, p in PROJECTS.items():
        h = hist[hist["project"] == name]
        # Typical capacity factor by month and hour of day
        shape = h.groupby(["month", "hour"])["capacity_factor"].mean()
        # Price the project captured in each month of the history year
        cap = h.groupby("month")[["price_eur_mwh", "generation_mwh"]].apply(
            lambda x: np.average(x["price_eur_mwh"], weights=x["generation_mwh"])
            if x["generation_mwh"].sum() > 0 else x["price_eur_mwh"].mean()
        )
        for m in months:
            days = pd.Period(f"{ANALYSIS_YEAR}-{m:02d}").days_in_month
            gen = shape.loc[m].sum() * days * p["capacity_mw"]
            out.append(
                {
                    "project": name,
                    "month": m,
                    "forecast_generation_mwh": gen,
                    "forecast_capture_price_eur_mwh": cap.loc[m],
                    "forecast_settlement_eur": (cap.loc[m] - p["strike_eur_mwh"]) * gen,
                }
            )
    return pd.DataFrame(out)


# actuals
def monthly_actuals(hourly: pd.DataFrame) -> pd.DataFrame:
    a = hourly[hourly["year"] == ANALYSIS_YEAR].copy()
    a["revenue_at_market_eur"] = a["price_eur_mwh"] * a["generation_mwh"]
    m = a.groupby(["project", "month"]).agg(
        actual_generation_mwh=("generation_mwh", "sum"),
        revenue_at_market_eur=("revenue_at_market_eur", "sum"),
        actual_settlement_eur=("settlement_eur", "sum"),
        baseload_price_eur_mwh=("price_eur_mwh", "mean"),
        hours=("generation_mwh", "size"),
    ).reset_index()
    # Keep only complete months (the source ends mid-day in local time)
    days = m["month"].map(lambda mo: pd.Period(f"{ANALYSIS_YEAR}-{mo:02d}").days_in_month)
    m = m[m["hours"] >= days * 24 * 0.98].copy()  # tolerate a few missing hours
    m["actual_capture_price_eur_mwh"] = m["revenue_at_market_eur"] / m["actual_generation_mwh"]
    m["capture_rate"] = m["actual_capture_price_eur_mwh"] / m["baseload_price_eur_mwh"]
    cap = m["project"].map({k: v["capacity_mw"] for k, v in PROJECTS.items()})
    m["capacity_factor"] = m["actual_generation_mwh"] / (cap * m["hours"])
    strike = m["project"].map({k: v["strike_eur_mwh"] for k, v in PROJECTS.items()})
    # Net cost of the renewable energy to the buyer after the VPPA settlement
    m["net_cost_eur_mwh"] = strike - m["actual_capture_price_eur_mwh"]
    return m.drop(columns="revenue_at_market_eur")


def variance_analysis(report: pd.DataFrame) -> pd.DataFrame:
    """Volume effect: change in generation at the budget spread.
    Price effect: change in captured price on the actual generation."""
    r = report.copy()
    strike = r["project"].map({k: v["strike_eur_mwh"] for k, v in PROJECTS.items()})
    fc_spread = r["forecast_capture_price_eur_mwh"] - strike
    r["volume_variance_eur"] = (r["actual_generation_mwh"] - r["forecast_generation_mwh"]) * fc_spread
    r["price_variance_eur"] = (
        r["actual_capture_price_eur_mwh"] - r["forecast_capture_price_eur_mwh"]
    ) * r["actual_generation_mwh"]
    r["total_variance_eur"] = r["actual_settlement_eur"] - r["forecast_settlement_eur"]
    return r


# invoices
def simulated_invoices(actuals: pd.DataFrame) -> pd.DataFrame:
    """Invoices from the counterparty. These are simulated: a copy of my results
    with two errors added on purpose, so the reconciliation has something to find."""
    inv = actuals[["project", "month", "actual_generation_mwh", "actual_settlement_eur"]].copy()
    inv.columns = ["project", "month", "invoiced_generation_mwh", "invoiced_settlement_eur"]
    months = sorted(inv["month"].unique())
    # Error 1: metered volume overstated by 3% for one wind month
    i1 = (inv["project"] == "Wind VPPA") & (inv["month"] == months[min(2, len(months) - 1)])
    inv.loc[i1, "invoiced_generation_mwh"] *= 1.03
    inv.loc[i1, "invoiced_settlement_eur"] *= 1.03
    # Error 2: settlement computed with a wrong strike price for one solar month
    i2 = (inv["project"] == "Solar VPPA") & (inv["month"] == months[min(5, len(months) - 1)])
    gen = inv.loc[i2, "invoiced_generation_mwh"]
    inv.loc[i2, "invoiced_settlement_eur"] -= 2.0 * gen  # strike invoiced 2 EUR/MWh higher
    return inv


def reconcile(actuals: pd.DataFrame, invoices: pd.DataFrame) -> pd.DataFrame:
    r = actuals[["project", "month", "actual_generation_mwh", "actual_settlement_eur"]].merge(
        invoices, on=["project", "month"]
    )
    r["volume_diff_pct"] = r["invoiced_generation_mwh"] / r["actual_generation_mwh"] - 1
    r["settlement_diff_eur"] = r["invoiced_settlement_eur"] - r["actual_settlement_eur"]
    base = r["actual_settlement_eur"].abs().clip(lower=1)
    r["flag"] = np.where(
        (r["volume_diff_pct"].abs() > INVOICE_TOLERANCE)
        | (r["settlement_diff_eur"].abs() / base > INVOICE_TOLERANCE),
        "REVIEW",
        "OK",
    )
    return r


# charts
def _style(ax, title, subtitle=""):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=BRAND, pad=24 if subtitle else 12)
    if subtitle:
        ax.text(0, 1.03, subtitle, transform=ax.transAxes, fontsize=10, color=INK_2)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#bdbab3")
    ax.tick_params(colors=INK_2, length=0, labelsize=10)


def _footer(fig):
    fig.text(0.01, 0.01, SOURCE, fontsize=8, color=MUTED)


def charts(report: pd.DataFrame) -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    months = sorted(report["month"].unique())
    lab = [pd.Timestamp(2020, m, 1).strftime("%b") for m in months]
    x = np.arange(len(months))
    by = {name: g.set_index("month").reindex(months) for name, g in report.groupby("project", sort=False)}

    # 1. Generation: bars = actual, short dark marks = budget
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), facecolor=SURFACE)
    for ax, (name, g) in zip(axes, by.items()):
        act, bud = g["actual_generation_mwh"] / 1000, g["forecast_generation_mwh"] / 1000
        ax.bar(x, act, width=0.62, color=COLORS[name], label="Actual")
        ax.hlines(bud, x - 0.36, x + 0.36, color=INK, linewidth=2.2, label="Budget")
        diff = act.sum() / bud.sum() - 1
        _style(ax, f"{SHORT[name]}: monthly generation (GWh)", f"Total {act.sum():,.0f} GWh, {diff:+.1%} vs budget")
        i = int(np.argmax(np.abs(act.values / bud.values - 1)))
        d = act.values[i] / bud.values[i] - 1
        ax.annotate(f"{d:+.0%}", (x[i], max(act.values[i], bud.values[i])), xytext=(0, 6),
                    textcoords="offset points", ha="center", fontsize=10, fontweight="bold", color=INK)
        ax.set_xticks(x, lab)
        ax.set_ylim(0, max(act.max(), bud.max()) * 1.18)
        ax.legend(frameon=False, fontsize=9, labelcolor=INK_2, loc="upper right")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig)
    fig.savefig(CHARTS / "generation_actual_vs_forecast.png", dpi=160)
    plt.close(fig)

    # 2. Cumulative cost to the buyer (settlement with the sign flipped): actual vs budget
    fig, ax = plt.subplots(figsize=(12, 4.8), facecolor=SURFACE)
    gap = 0
    for name, g in by.items():
        act = -g["actual_settlement_eur"].cumsum() / 1e6
        bud = -g["forecast_settlement_eur"].cumsum() / 1e6
        gap += act.iloc[-1] - bud.iloc[-1]
        ax.plot(x, bud, color=COLORS[name], lw=1.6, ls="--", alpha=0.8)
        ax.plot(x, act, color=COLORS[name], lw=2.6, marker="o", ms=5)
        ax.annotate(f"{SHORT[name]} actual  {act.iloc[-1]:.1f}", (x[-1], act.iloc[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=10, color=TEXT[name], fontweight="bold")
        ax.annotate(f"{SHORT[name]} budget  {bud.iloc[-1]:.1f}", (x[-1], bud.iloc[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=9, color=INK_2)
    ax.axhline(0, color="#bdbab3", lw=1)
    ax.set_xticks(x, lab)
    ax.set_xlim(-0.3, len(x) + 1.6)
    _style(ax, "Cumulative amount paid by the buyer to the plants (EUR million)",
           f"Solid line = actual, dashed = budget. After {len(x)} months the buyer paid EUR {gap:.1f} million more than budgeted")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig)
    fig.savefig(CHARTS / "cumulative_settlement.png", dpi=160)
    plt.close(fig)

    # 3. Capture rate with the lowest month marked
    fig, ax = plt.subplots(figsize=(12, 4.6), facecolor=SURFACE)
    ax.axhline(100, color=MUTED, lw=1, ls=":")
    # the 100% reference is named on the axis, so it never collides with the data labels
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: "market avg 100%" if abs(v - 100) < 1e-6 else f"{v:.0f}%"))
    for name, g in by.items():
        cr = g["capture_rate"] * 100
        ax.plot(x, cr, color=COLORS[name], lw=2.4, marker="o", ms=6)
        ax.annotate(SHORT[name], (x[-1], cr.iloc[-1]), xytext=(10, 0), textcoords="offset points",
                    va="center", fontsize=10, fontweight="bold", color=TEXT[name])
        i = int(np.argmin(cr.values))
        ax.annotate(f"{lab[i]}: {cr.values[i]:.0f}%", (x[i], cr.values[i]), xytext=(0, -16),
                    textcoords="offset points", ha="center", fontsize=9, color=TEXT[name])
    ax.set_xticks(x, lab)
    ax.set_xlim(-0.4, len(x) - 0.2)
    lo = min(g["capture_rate"].min() for g in by.values()) * 100
    ax.set_ylim(lo - 10, max(110, max(g["capture_rate"].max() for g in by.values()) * 100 + 5))
    _style(ax, "Capture rate: price earned per MWh as % of the average market price",
           "Below 100% means the plant produced mostly in hours with cheaper electricity")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig)
    fig.savefig(CHARTS / "capture_rate.png", dpi=160)
    plt.close(fig)


# main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="use synthetic data to test the code")
    args = ap.parse_args()

    df = load_data(args.demo)
    hourly = project_hourly(df)
    actuals = monthly_actuals(hourly)
    months = sorted(actuals["month"].unique())
    forecast = budget_forecast(hourly, months)
    report = variance_analysis(actuals.merge(forecast, on=["project", "month"]))
    recon = reconcile(actuals, simulated_invoices(actuals))

    OUT.mkdir(parents=True, exist_ok=True)
    report.round(3).to_csv(OUT / "monthly_portfolio_report.csv", index=False)
    recon.round(3).to_csv(OUT / "invoice_reconciliation.csv", index=False)

    with duckdb.connect(str(OUT / "portfolio.duckdb")) as con:
        con.execute("CREATE OR REPLACE TABLE hourly AS SELECT * FROM hourly")
        con.execute("CREATE OR REPLACE TABLE monthly_report AS SELECT * FROM report")
        con.execute("CREATE OR REPLACE TABLE invoice_reconciliation AS SELECT * FROM recon")

    charts(report)

    # Hour of day x month view of the settlement, and simple data quality figures
    h20 = hourly[(hourly["year"] == ANALYSIS_YEAR) & (hourly["month"].isin(report["month"].unique()))]
    heat = h20.groupby(["project", "month", "hour"]).agg(
        generation_mwh=("generation_mwh", "sum"), settlement_eur=("settlement_eur", "sum")).reset_index()
    heat.round(3).to_csv(OUT / "settlement_by_hour.csv", index=False)
    checks = {
        "hours_loaded": int(len(df)),
        "years": f"{int(df['year'].min())} to {int(df['year'].max())}",
        "months_analysed": int(report["month"].nunique()),
        "negative_price_hours": int((df.loc[df["year"] == ANALYSIS_YEAR, "price_eur_mwh"] < 0).sum()),
    }
    pd.Series(checks).to_json(OUT / "data_checks.json")

    from build_dashboard import build
    build(report, recon, heat, checks)

    tot = report.groupby("project").agg(
        gen=("actual_generation_mwh", "sum"), fc=("forecast_generation_mwh", "sum"),
        sett=("actual_settlement_eur", "sum"), fc_sett=("forecast_settlement_eur", "sum"),
        vol=("volume_variance_eur", "sum"), price=("price_variance_eur", "sum"),
    )
    period = f"{pd.Timestamp(2020, months[0], 1):%b}-{pd.Timestamp(2020, months[-1], 1):%b} {ANALYSIS_YEAR}"
    lines = [f"# Results summary ({'DEMO DATA' if args.demo else 'OPSD Germany data'}, {period})", ""]
    lines.append("| Project | Generation (GWh) | vs budget | Settlement (EUR M) | Budget (EUR M) | Volume effect (EUR M) | Price effect (EUR M) |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for name, r in tot.iterrows():
        lines.append(
            f"| {name} | {r.gen/1000:,.1f} | {r.gen/r.fc-1:+.1%} | {r.sett/1e6:,.2f} | "
            f"{r.fc_sett/1e6:,.2f} | {r.vol/1e6:,.2f} | {r.price/1e6:,.2f} |"
        )
    flagged = recon[recon["flag"] == "REVIEW"]
    lines += ["", f"Invoice lines flagged for review: {len(flagged)} of {len(recon)}"]
    for _, r in flagged.iterrows():
        lines.append(
            f"- {r.project}, month {r.month}: volume diff {r.volume_diff_pct:+.1%}, "
            f"settlement diff EUR {r.settlement_diff_eur:,.0f}"
        )
    (OUT / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
