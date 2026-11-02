"""Builds docs/index.html, the interactive version of the analysis.

Reads the files written by portfolio_analytics.py, so run that first:
    python src/build_dashboard.py
The data goes inside the HTML and Plotly loads from its CDN, so the page can be
published with GitHub Pages from the docs folder.
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
DOCS = ROOT / "docs"
REPO_URL = "https://github.com/melimape/ppa-settlement-analysis-germany"
LINKEDIN_URL = "https://www.linkedin.com/in/melissa-aristizabal"
PLOTLY_SRC = "https://cdn.plot.ly/plotly-2.35.2.min.js"
STRIKES = {"Solar VPPA": 45.0, "Wind VPPA": 50.0}  # same contract prices as portfolio_analytics.py


def build(report=None, recon=None, heat=None, checks=None, plotly_src: str = PLOTLY_SRC) -> Path:
    if report is None:
        report = pd.read_csv(OUT / "monthly_portfolio_report.csv")
    if recon is None:
        recon = pd.read_csv(OUT / "invoice_reconciliation.csv")
    if heat is None:
        heat = pd.read_csv(OUT / "settlement_by_hour.csv")
    if checks is None:
        checks = json.loads((OUT / "data_checks.json").read_text())
    cols = [
        "project", "month", "actual_generation_mwh", "forecast_generation_mwh",
        "actual_settlement_eur", "forecast_settlement_eur", "volume_variance_eur",
        "price_variance_eur", "capture_rate", "actual_capture_price_eur_mwh",
        "baseload_price_eur_mwh",
    ]
    data = {
        "report": report[cols].round(4).to_dict(orient="records"),
        "recon": recon[["project", "month", "volume_diff_pct", "settlement_diff_eur", "flag"]]
        .round(4).to_dict(orient="records"),
        "heat": heat[["project", "month", "hour", "generation_mwh", "settlement_eur"]].round(2).to_dict(orient="records"),
        "checks": checks,
        "strikes": STRIKES,
    }
    html = (TEMPLATE.replace("__DATA__", json.dumps(data)).replace("__PLOTLY__", plotly_src)
            .replace("__REPO__", REPO_URL).replace("__LINKEDIN__", LINKEDIN_URL))
    DOCS.mkdir(exist_ok=True)
    path = DOCS / "index.html"
    path.write_text(html, encoding="utf-8")
    print(f"Dashboard saved to {path}")
    return path


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Solar and wind PPA settlement, Germany 2020 | Melissa Aristizabal</title>
<meta name="description" content="Settlement, budget variance and invoice checks for two virtual PPAs in Germany, built by Melissa Aristizabal, Energy Engineer.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="__PLOTLY__"></script>
<style>
  :root {
    --bg: #f6f4ee; --panel: #fcfbf8; --ink: #1b2a27; --ink2: #4a5a56; --muted: #8a9692; --line: #ded9cc;
    --dark: #13302b; --teal: #2e7d6a; --amber: #e9a23b; --amber-text: #b5701a; --mint: #bfd8d2; --red: #b4452f;
    --head: "Space Grotesk", "DM Sans", system-ui, sans-serif; --body: "DM Sans", system-ui, sans-serif;
    --mono: "JetBrains Mono", ui-monospace, monospace;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 15px; }
  a { color: inherit; }
  .wrap { max-width: 1160px; margin: 0 auto; padding: 0 24px 56px; }

  .topbar { display: flex; justify-content: space-between; align-items: center; padding: 18px 0 12px;
            border-bottom: 1px solid var(--line); font-size: 12px; gap: 12px; flex-wrap: wrap; }
  .who { font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--ink); text-decoration: none; }
  .who b { color: var(--teal); } .who .role { color: var(--ink2); }
  .nav { color: var(--ink2); }
  .nav a { margin-left: 18px; text-decoration: none; border-bottom: 1.5px solid var(--amber); padding-bottom: 1px; }

  .eyebrow { font-family: var(--mono); font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--teal); margin: 0 0 8px; }
  .intro { display: grid; grid-template-columns: 1fr auto; gap: 28px; align-items: end; padding: 40px 0 26px; }
  h1 { font-family: var(--head); font-weight: 700; font-size: 38px; line-height: 1.08; letter-spacing: -.02em; margin: 0; }
  h1 em { font-style: normal; color: var(--teal); }
  .lead { color: var(--ink2); margin: 14px 0 0; max-width: 640px; line-height: 1.6; }

  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: 999px; padding: 3px; background: var(--panel); }
  .seg button { border: 0; background: transparent; padding: 8px 16px; border-radius: 999px; font: 500 14px var(--body);
                color: var(--ink2); cursor: pointer; }
  .seg button.on { background: var(--dark); color: #fff; }
  .seg button:focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }

  .kpis { display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
  .kpi { padding: 18px 20px 18px 0; }
  .kpi + .kpi { padding-left: 20px; border-left: 1px solid var(--line); }
  .kpi .label { font-size: 13px; color: var(--ink2); }
  .kpi .value { font-family: var(--head); font-size: 32px; font-weight: 600; margin: 6px 0 2px; letter-spacing: -.01em; font-variant-numeric: tabular-nums; }
  .kpi .note { font-size: 13px; color: var(--muted); }
  .bad { color: var(--red); font-weight: 700; } .good { color: var(--teal); font-weight: 700; }

  .note-box { margin: 26px 0 8px; background: var(--dark); color: #e9eeec; border-radius: 10px; padding: 24px 26px;
              display: grid; grid-template-columns: 1.25fr 1fr; gap: 30px; }
  .note-box h2 { font-family: var(--head); font-size: 15px; font-weight: 600; color: var(--amber); margin: 0 0 12px;
                 letter-spacing: .02em; }
  .note-box ol, .note-box ul { margin: 0; padding-left: 20px; line-height: 1.55; }
  .note-box li { margin-bottom: 8px; }
  .note-box li b { color: #fff; }
  .note-box .sig { font-size: 12px; color: var(--mint); margin-top: 12px; font-family: var(--mono); }

  section.block { margin-top: 36px; }
  .block > .eyebrow { margin-bottom: 4px; }
  .block > h3 { font-family: var(--head); font-size: 22px; font-weight: 600; margin: 0 0 14px; letter-spacing: -.01em; }
  .grid { display: grid; grid-template-columns: 1.6fr 1fr; gap: 16px; }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 18px 18px 8px; }
  .card h4 { font-size: 15px; font-weight: 700; margin: 0; }
  .card p.sub { font-size: 13px; color: var(--ink2); margin: 4px 0 0; line-height: 1.45; }
  .chart { height: 300px; }
  .key { display: flex; gap: 18px; flex-wrap: wrap; font-size: 12px; color: var(--ink2); margin-top: 8px; }
  .key i { display: inline-block; width: 18px; height: 0; border-top: 2px solid var(--ink2); vertical-align: middle; margin-right: 6px; }

  table { width: 100%; border-collapse: collapse; font-size: 14px; margin: 10px 0 12px; }
  th { text-align: left; font-weight: 500; color: var(--muted); border-bottom: 1px solid var(--line); padding: 8px 6px; font-size: 12px;
       text-transform: uppercase; letter-spacing: .05em; }
  td { padding: 9px 6px; border-bottom: 1px solid var(--line); }
  td.num { text-align: right; font-family: var(--mono); font-size: 13px; }
  th.num { text-align: right; }
  .tag { font-family: var(--mono); font-size: 12px; font-weight: 500; }
  .tag.review { color: var(--red); } .tag.ok { color: var(--teal); }
  .sw { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 8px; }
  dl.checks { display: grid; grid-template-columns: 1fr auto; gap: 0; margin: 10px 0 12px; font-size: 14px; }
  dl.checks dt, dl.checks dd { padding: 9px 0; border-bottom: 1px solid var(--line); margin: 0; }
  dl.checks dd { font-family: var(--mono); font-size: 13px; text-align: right; }

  .method { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
  .method div { border-top: 2px solid var(--teal); padding-top: 12px; font-size: 14px; line-height: 1.55; color: var(--ink2); }
  .method b { display: block; color: var(--ink); margin-bottom: 4px; }
  .method .ai { border-top-color: var(--amber); }

  footer { margin-top: 40px; padding-top: 14px; border-top: 1px solid var(--line); font-size: 12px; color: var(--muted);
           line-height: 1.6; display: flex; justify-content: space-between; gap: 20px; flex-wrap: wrap; }

  @media (max-width: 880px) {
    .intro, .grid, .note-box, .method { grid-template-columns: 1fr; }
    .kpis { grid-template-columns: repeat(2, 1fr); }
    .kpi:nth-child(3) { padding-left: 0; border-left: 0; }
    .kpi:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
  }
  @media (max-width: 520px) { h1 { font-size: 28px; } .kpi .value { font-size: 23px; } .wrap { padding: 0 14px 40px; }
    .nav a { margin: 0 14px 0 0; } table { font-size: 12px; } .note-box { padding: 20px; } }
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <a class="who" href="__LINKEDIN__"><b>Melissa Aristizabal</b> <span class="role">| Energy Engineer</span></a>
    <div class="nav"><a href="__REPO__">Code</a><a href="__LINKEDIN__">LinkedIn</a></div>
  </div>

  <section class="intro">
    <div>
      <p class="eyebrow">Case study | Renewable PPA analytics</p>
      <h1>Solar and wind PPA settlement,<br><em>Germany 2020</em></h1>
      <p class="lead">I settled two virtual PPAs, a 100 MW solar plant and a 150 MW wind farm, hour by hour against the German
        day-ahead price from January to September 2020, and compared the result with a budget built only from 2019 data.
        The contracts are hypothetical. Prices and generation profiles are real.</p>
    </div>
    <div class="seg" id="seg" role="group" aria-label="Choose contracts">
      <button data-v="all" class="on">Solar + Wind</button>
      <button data-v="Solar VPPA">Solar</button>
      <button data-v="Wind VPPA">Wind</button>
    </div>
  </section>

  <section class="kpis" id="kpis"></section>

  <section class="note-box">
    <div>
      <h2>What Finance needs to know</h2>
      <ol id="findings"></ol>
    </div>
    <div>
      <h2>What I would do next</h2>
      <ul>
        <li><b>Budget with price scenarios,</b> not a single price path. A low price case would have covered most of this gap.</li>
        <li><b>Track capture rate every month</b> as an early warning; it moved before the cost did.</li>
        <li><b>Hold payment on the flagged invoices</b> until the counterparty explains the difference.</li>
      </ul>
      <p class="sig">Analyst note | M. Aristizabal</p>
    </div>
  </section>

  <section class="block">
    <p class="eyebrow">01 | Cost</p>
    <h3>Where the money went</h3>
    <div class="grid">
      <div class="card">
        <h4>Cumulative payments to the plants, EUR million</h4>
        <div class="key"><span><i></i>Actual</span><span><i style="border-top-style:dashed"></i>Budget</span></div>
        <div class="chart" id="c_cum"></div>
      </div>
      <div class="card">
        <h4>From budget to actual, EUR million</h4>
        <p class="sub">Red adds cost, green reduces it.</p>
        <div class="chart" id="c_bridge"></div>
      </div>
    </div>
  </section>

  <section class="block">
    <p class="eyebrow">02 | Price</p>
    <h3>Why the buyer paid more</h3>
    <div class="grid">
      <div class="card">
        <h4>Captured price vs contract price, EUR/MWh</h4>
        <p class="sub">The buyer pays the gap between the dotted contract line and the price each plant actually captured. Pick Solar or Wind to shade the gap.</p>
        <div class="chart" id="c_price"></div>
      </div>
      <div class="card">
        <h4>Capture rate</h4>
        <p class="sub">Captured price as % of the monthly average price.</p>
        <div class="chart" id="c_cap"></div>
      </div>
    </div>
  </section>

  <section class="block">
    <p class="eyebrow">03 | Timing</p>
    <h3>When the contracts cost the most</h3>
    <div class="card">
      <h4>Average payment per MWh produced, by hour of day and month, EUR/MWh</h4>
      <p class="sub">Darker cells are the hours where each MWh cost the buyer more. The lightest cells are hours where the buyer paid little or received money. Empty cells had no generation. Local time.</p>
      <div class="chart" id="c_heat" style="height:330px"></div>
    </div>
  </section>

  <section class="block">
    <p class="eyebrow">04 | Volume</p>
    <h3>Generation against budget</h3>
    <div class="card">
      <h4>Monthly generation, GWh</h4>
      <p class="sub">Bars are actual generation, short black marks are the budget.</p>
      <div class="chart" id="c_gen" style="height:260px"></div>
    </div>
  </section>

  <section class="block">
    <p class="eyebrow">05 | Controls</p>
    <h3>Invoice and data checks</h3>
    <div class="grid">
      <div class="card">
        <h4>Invoice check</h4>
        <p class="sub">Counterparty invoices (simulated) against my own settlement calculation, 1% tolerance.</p>
        <table id="tbl"></table>
      </div>
      <div class="card">
        <h4>Data checks</h4>
        <p class="sub">Run every time the pipeline loads new data.</p>
        <dl class="checks" id="checks"></dl>
      </div>
    </div>
  </section>

  <section class="block">
    <p class="eyebrow">06 | Method</p>
    <h3>How it was built</h3>
    <div class="method">
      <div><b>Settlement</b>Every hour: (market price minus contract price) x generation. Contract prices are 45 EUR/MWh for
        solar and 50 EUR/MWh for wind. Plant output is the German national capacity factor scaled to each plant.</div>
      <div><b>Budget and variance</b>The 2020 budget uses only 2019 shapes and captured prices. The gap is split into a volume
        effect (more or less energy) and a price effect (higher or lower captured price).</div>
      <div class="ai"><b>Tools and AI use</b>Python, SQL (DuckDB) and Plotly. I used Claude as a coding assistant and checked
        every result myself: the variance effects add up to the total gap, and the invoice check catches the two errors planted on purpose.</div>
    </div>
  </section>

  <footer>
    <span>Data: <a href="https://data.open-power-system-data.org/time_series/2020-10-06/">Open Power System Data</a>, time series 2020-10-06.
      Solar capacity for 2020 uses the last 2019 value, so solar output may be slightly overstated.</span>
    <span>Melissa Aristizabal | <a href="__REPO__">GitHub</a></span>
  </footer>
</div>

<script>
const DATA = __DATA__;
const C = { "Solar VPPA": "#e9a23b", "Wind VPPA": "#2e7d6a" };
const T = { "Solar VPPA": "#b5701a", "Wind VPPA": "#2e7d6a" };   // darker solar for text on light background
const NAME = { "Solar VPPA": "Solar", "Wind VPPA": "Wind" };
const MON = ["", "Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const FONT = { family: "DM Sans, system-ui, sans-serif", size: 12, color: "#4a5a56" };
const BASE = {
  margin: { l: 40, r: 16, t: 10, b: 32 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
  font: FONT, hovermode: "x unified", showlegend: false,
  xaxis: { showgrid: false, linecolor: "#cfc9ba", tickfont: FONT, fixedrange: true },
  yaxis: { gridcolor: "#ebe7dc", zeroline: false, tickfont: FONT, fixedrange: true },
  hoverlabel: { bgcolor: "#13302b", font: { color: "#fff", family: FONT.family, size: 12 }, bordercolor: "#13302b" },
};
const CFG = { displayModeBar: false, responsive: true };
const projects = [...new Set(DATA.report.map(r => r.project))];
const months = [...new Set(DATA.report.map(r => r.month))].sort((a, b) => a - b);
const X = months.map(m => MON[m]);
const rows = p => months.map(m => DATA.report.find(r => r.project === p && r.month === m));
const sum = a => a.reduce((s, v) => s + v, 0);
const cumsum = a => { let s = 0; return a.map(v => (s += v)); };
const fmt = (v, d = 1) => v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const sgn = (v, d = 1) => (v > 0 ? "+" : "") + fmt(v, d);
const layout = extra => Object.assign({}, BASE, extra, {
  xaxis: Object.assign({}, BASE.xaxis, extra && extra.xaxis), yaxis: Object.assign({}, BASE.yaxis, extra && extra.yaxis) });
const label = (p, x, y, text, opts = {}) => Object.assign({ x, y, text, showarrow: false, xanchor: "left", xshift: 8,
  font: { color: T[p], size: 12, family: FONT.family } }, opts);

// data checks do not depend on the selection
const ck = DATA.checks;
document.getElementById("checks").innerHTML = `
  <dt>Hours loaded (${ck.years})</dt><dd>${Number(ck.hours_loaded).toLocaleString("en-US")}</dd>
  <dt>Complete months analysed</dt><dd>${ck.months_analysed}</dd>
  <dt>Hours with negative prices in 2020</dt><dd>${ck.negative_price_hours}</dd>
  <dt>Variance effects add up to the total gap</dt><dd class="tag ok" id="ck_sum"></dd>`;

function render(view) {
  const sel = view === "all" ? projects : [view];
  const R = DATA.report.filter(r => sel.includes(r.project));
  const paid = -sum(R.map(r => r.actual_settlement_eur)) / 1e6;       // positive = buyer paid the plants
  const bud = -sum(R.map(r => r.forecast_settlement_eur)) / 1e6;
  const gen = sum(R.map(r => r.actual_generation_mwh)) / 1e3;
  const genB = sum(R.map(r => r.forecast_generation_mwh)) / 1e3;
  const volCost = -sum(R.map(r => r.volume_variance_eur)) / 1e6;
  const priceCost = -sum(R.map(r => r.price_variance_eur)) / 1e6;
  const inv = DATA.recon.filter(r => sel.includes(r.project));
  const flagged = inv.filter(r => r.flag === "REVIEW").sort((a, b) => a.month - b.month);
  const gap = paid - bud;
  document.getElementById("ck_sum").textContent = Math.abs(volCost + priceCost - gap) < 0.01 ? "Yes" : "Check";

  document.getElementById("kpis").innerHTML = `
    <div class="kpi"><div class="label">Paid to the plants</div><div class="value">EUR ${fmt(paid)}M</div><div class="note">budget EUR ${fmt(bud)}M</div></div>
    <div class="kpi"><div class="label">Over budget</div><div class="value">${gap >= 0 ? "+" : "-"}EUR ${fmt(Math.abs(gap))}M</div>
      <div class="note"><span class="${gap >= 0 ? "bad" : "good"}">${sgn(100 * gap / bud, 0)}%</span> vs budget</div></div>
    <div class="kpi"><div class="label">Generation</div><div class="value">${fmt(gen, 0)} GWh</div><div class="note">${sgn(100 * (gen / genB - 1))}% vs budget</div></div>
    <div class="kpi"><div class="label">Net cost per MWh</div><div class="value">EUR ${fmt(paid * 1e6 / (gen * 1e3))}</div><div class="note">contract minus captured price</div></div>`;

  // Findings written from the numbers
  let low = null;
  sel.forEach(p => rows(p).forEach(r => { if (!low || r.capture_rate < low.capture_rate) low = r; }));
  const disputed = sum(flagged.map(r => Math.abs(r.settlement_diff_eur)));
  const f1 = Math.abs(priceCost) >= Math.abs(volCost)
    ? `<b>Prices, not production, explain the gap.</b> Lower captured prices added EUR ${fmt(priceCost, 2)}M of cost; ` +
      (Math.abs(volCost) < 0.01 ? `the volume effects of the two plants cancel each other out.` : `generation changed it by only EUR ${sgn(volCost, 2)}M.`)
    : `<b>Production explains most of the gap:</b> EUR ${sgn(volCost, 2)}M from volume against EUR ${sgn(priceCost, 2)}M from prices.`;
  const f2 = `<b>Lowest capture rate: ${NAME[low.project]} in ${MON[low.month]}, ${fmt(low.capture_rate * 100, 0)}%</b> of the average market price. That is the month where each MWh was worth least to the buyer.`;
  const f3 = flagged.length
    ? `<b>${flagged.length} invoice line${flagged.length > 1 ? "s" : ""} should not be paid yet:</b> EUR ${Math.round(disputed).toLocaleString("en-US")} in differences against my calculation.`
    : `<b>All invoices match</b> my settlement calculation within 1%.`;
  document.getElementById("findings").innerHTML = [f1, f2, f3].map(t => `<li>${t}</li>`).join("");

  // 01 Cumulative payments
  const tc = [], ann = [];
  sel.forEach(p => {
    const r = rows(p);
    const b = cumsum(r.map(v => -v.forecast_settlement_eur / 1e6)), a = cumsum(r.map(v => -v.actual_settlement_eur / 1e6));
    tc.push({ x: X, y: b, mode: "lines", line: { color: C[p], width: 2, dash: "dash" }, opacity: 0.8, hovertemplate: "%{y:.2f}<extra>" + NAME[p] + " budget</extra>" });
    tc.push({ x: X, y: a, mode: "lines+markers", line: { color: C[p], width: 3.5 }, marker: { size: 7, line: { color: "#fcfbf8", width: 1.5 } },
      hovertemplate: "%{y:.2f}<extra>" + NAME[p] + " actual</extra>" });
    ann.push(label(p, X[X.length - 1], a[a.length - 1], "<b>" + NAME[p] + "</b> " + fmt(a[a.length - 1])));
  });
  Plotly.react("c_cum", tc, layout({ yaxis: { rangemode: "tozero" }, annotations: ann, margin: { l: 40, r: 78, t: 10, b: 32 } }), CFG);

  // 01 Bridge
  Plotly.react("c_bridge", [{
    type: "waterfall", x: ["Budget", "Volume", "Price", "Actual"], measure: ["absolute", "relative", "relative", "total"],
    y: [bud, volCost, priceCost, 0], text: [fmt(bud, 2), Math.abs(volCost) < 0.005 ? "0.00" : sgn(volCost, 2), sgn(priceCost, 2), fmt(paid, 2)],
    textposition: "outside", textfont: { family: "JetBrains Mono, monospace", size: 12, color: "#1b2a27" }, cliponaxis: false,
    connector: { line: { color: "#cfc9ba", width: 1, dash: "dot" } },
    increasing: { marker: { color: "#b4452f" } }, decreasing: { marker: { color: "#8fb3ab" } }, totals: { marker: { color: "#13302b" } },
    hovertemplate: "%{x}: %{text}<extra></extra>",
  }], layout({ hovermode: "closest", yaxis: { rangemode: "tozero" }, margin: { l: 40, r: 16, t: 26, b: 32 } }), CFG);

  // 02 Captured price vs contract price
  const base = rows(projects[0]).map(v => v.baseload_price_eur_mwh);
  const tp = [{ x: X, y: base, mode: "lines", line: { color: "#8a9692", width: 2 }, hovertemplate: "%{y:.1f}<extra>Average market price</extra>" }];
  // label the market line in the month where it sits furthest above the captured prices
  let li = 0, best = -Infinity;
  base.forEach((b, i) => { const top = Math.max(...sel.map(p => rows(p)[i].actual_capture_price_eur_mwh)); if (b - top > best) { best = b - top; li = i; } });
  const pa = [{ x: X[li], y: base[li], text: "Average market price", showarrow: false, yshift: best > 0 ? 12 : -12,
    font: { color: "#8a9692", size: 11 } }];
  sel.forEach(p => {
    const cp = rows(p).map(v => v.actual_capture_price_eur_mwh), k = DATA.strikes[p];
    tp.push({ x: X, y: X.map(() => k), mode: "lines", line: { color: C[p], width: 1.5, dash: "dot" }, hovertemplate: "%{y:.0f}<extra>" + NAME[p] + " contract</extra>" });
    tp.push({ x: X, y: cp, mode: "lines+markers", line: { color: C[p], width: 3.5 }, marker: { size: 7, line: { color: "#fcfbf8", width: 1.5 } },
      fill: sel.length === 1 ? "tonexty" : "none", fillcolor: p === "Solar VPPA" ? "rgba(233,162,59,0.12)" : "rgba(46,125,106,0.10)",
      hovertemplate: "%{y:.1f}<extra>" + NAME[p] + " captured</extra>" });
    pa.push({ x: X[X.length - 1], y: k, text: NAME[p] + " contract " + k, showarrow: false, xanchor: "right", yshift: 10, font: { color: T[p], size: 11 } });
  });
  Plotly.react("c_price", tp, layout({ yaxis: { rangemode: "tozero" }, annotations: pa }), CFG);

  // 02 Capture rate
  const tcap = sel.map(p => ({ x: X, y: rows(p).map(v => v.capture_rate * 100), mode: "lines+markers", line: { color: C[p], width: 3.5 },
    marker: { size: 7, line: { color: "#fcfbf8", width: 1.5 } }, hovertemplate: "%{y:.0f}%<extra>" + NAME[p] + "</extra>" }));
  const capAnn = sel.map(p => { const r = rows(p); return label(p, X[X.length - 1], r[r.length - 1].capture_rate * 100, "<b>" + NAME[p] + "</b>"); });
  Plotly.react("c_cap", tcap, layout({ yaxis: { ticksuffix: "%" }, annotations: capAnn, margin: { l: 44, r: 54, t: 10, b: 32 },
    shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 100, y1: 100, line: { color: "#8a9692", width: 1, dash: "dot" } }] }), CFG);

  // 03 Heatmap: payment per MWh by hour and month
  const hours = [...Array(24).keys()];
  const H = DATA.heat.filter(r => sel.includes(r.project));
  const z = hours.map(h => months.map(m => {
    const c = H.filter(r => r.hour === h && r.month === m), g = sum(c.map(r => r.generation_mwh));
    return g > 0.5 ? -sum(c.map(r => r.settlement_eur)) / g : null;
  }));
  Plotly.react("c_heat", [{
    type: "heatmap", x: X, y: hours.map(h => String(h).padStart(2, "0") + ":00"), z, xgap: 2, ygap: 1, hoverongaps: false,
    colorscale: [[0, "#fcfbf8"], [0.35, "#bfd8d2"], [0.7, "#2e7d6a"], [1, "#13302b"]],
    zmin: 0, zmax: Math.max(...z.flat().filter(v => v !== null)),  // hours where the buyer received money show as the lightest color
    colorbar: { thickness: 10, outlinewidth: 0, tickfont: FONT, ticksuffix: " EUR", len: 0.9 },
    hovertemplate: "%{x}, %{y}: EUR %{z:.1f}/MWh<extra></extra>",
  }], layout({ hovermode: "closest", margin: { l: 52, r: 10, t: 6, b: 32 },
    yaxis: { autorange: "reversed", dtick: 3, gridcolor: "rgba(0,0,0,0)" } }), CFG);

  // 04 Monthly generation
  const tg = [], n = sel.length, w = n > 1 ? 0.38 : 0.6;
  sel.forEach((p, k) => {
    const r = rows(p), off = n > 1 ? (k - 0.5) * 0.4 : 0, xi = months.map((_, i) => i + off);
    tg.push({ type: "bar", x: xi, y: r.map(v => v.actual_generation_mwh / 1e3), width: w, marker: { color: C[p] },
      customdata: X, hovertemplate: "%{customdata}: %{y:.1f} GWh<extra>" + NAME[p] + " actual</extra>" });
    tg.push({ type: "scatter", mode: "markers", x: xi, y: r.map(v => v.forecast_generation_mwh / 1e3), customdata: X,
      marker: { symbol: "line-ew", size: n > 1 ? 18 : 30, line: { width: 3, color: "#1b2a27" } },
      hovertemplate: "%{customdata}: %{y:.1f} GWh<extra>" + NAME[p] + " budget</extra>" });
  });
  Plotly.react("c_gen", tg, layout({ barmode: "overlay", hovermode: "closest", xaxis: { tickvals: months.map((_, i) => i), ticktext: X } }), CFG);

  // 05 Invoices
  document.getElementById("tbl").innerHTML =
    `<tr><th>Contract</th><th>Month</th><th class="num">Volume</th><th class="num">Settlement</th><th>Status</th></tr>` +
    flagged.map(r => `<tr><td><span class="sw" style="background:${C[r.project]}"></span>${NAME[r.project]}</td><td>${MON[r.month]}</td>
      <td class="num">${sgn(r.volume_diff_pct * 100)}%</td><td class="num">EUR ${Math.round(r.settlement_diff_eur).toLocaleString("en-US")}</td>
      <td><span class="tag review">Review</span></td></tr>`).join("") +
    `<tr><td colspan="4" style="color:var(--muted)">${inv.length - flagged.length} other lines within 1%</td><td><span class="tag ok">OK</span></td></tr>`;
}

document.querySelectorAll("#seg button").forEach(b => b.addEventListener("click", () => {
  document.querySelectorAll("#seg button").forEach(x => x.classList.remove("on"));
  b.classList.add("on");
  render(b.dataset.v);
}));
render("all");
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
