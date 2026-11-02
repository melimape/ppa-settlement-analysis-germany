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

# Chart colors
COLORS = {"Solar VPPA": "#2a78d6", "Wind VPPA": "#eb6834"}
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


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
def _style(ax, title, ylabel):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=12)
    ax.set_ylabel(ylabel, color=INK_2)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, length=0)


def charts(report: pd.DataFrame) -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    labels = {m: pd.Timestamp(2020, m, 1).strftime("%b") for m in report["month"].unique()}

    # 1. Actual vs forecast generation, one panel per project (small multiples)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), facecolor=SURFACE, sharey=False)
    for ax, (name, g) in zip(axes, report.groupby("project", sort=False)):
        x = np.arange(len(g))
        ax.bar(x, g["actual_generation_mwh"] / 1000, width=0.6, color=COLORS[name], label="Actual")
        ax.plot(x, g["forecast_generation_mwh"] / 1000, color=INK_2, marker="o", ms=5,
                lw=1.5, ls="--", label="Budget forecast")
        ax.set_xticks(x, [labels[m] for m in g["month"]])
        _style(ax, f"{name}: actual vs budget", "GWh")
        ax.legend(frameon=False, fontsize=9, labelcolor=INK_2)
    fig.tight_layout()
    fig.savefig(CHARTS / "generation_actual_vs_forecast.png", dpi=160)
    plt.close(fig)

    # 2. Monthly VPPA settlement by project
    fig, ax = plt.subplots(figsize=(11, 4), facecolor=SURFACE)
    months = sorted(report["month"].unique())
    x = np.arange(len(months))
    w = 0.38
    for i, (name, g) in enumerate(report.groupby("project", sort=False)):
        g = g.set_index("month").reindex(months)
        ax.bar(x + (i - 0.5) * (w + 0.02), g["actual_settlement_eur"] / 1e6, width=w,
               color=COLORS[name], label=name)
    ax.axhline(0, color=INK_2, lw=1)
    ax.set_xticks(x, [labels[m] for m in months])
    _style(ax, "Monthly VPPA settlement (negative = buyer pays the developer)", "EUR million")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_2, ncol=2, loc="lower right", bbox_to_anchor=(1, 1.0))
    fig.tight_layout()
    fig.savefig(CHARTS / "monthly_settlement.png", dpi=160)
    plt.close(fig)

    # 3. Capture rate (project captured price / baseload price)
    fig, ax = plt.subplots(figsize=(11, 4), facecolor=SURFACE)
    for name, g in report.groupby("project", sort=False):
        ax.plot([labels[m] for m in g["month"]], g["capture_rate"] * 100, color=COLORS[name],
                lw=2, marker="o", ms=6, label=name)
    ax.axhline(100, color=INK_2, lw=1, ls=":")
    _style(ax, "Capture rate: price earned by each project vs average market price", "% of baseload price")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_2)
    fig.tight_layout()
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
