"""Run every query in sql/reporting_queries.sql against outputs/portfolio.duckdb."""

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]

con = duckdb.connect(str(ROOT / "outputs" / "portfolio.duckdb"), read_only=True)
for block in (ROOT / "sql" / "reporting_queries.sql").read_text().split(";"):
    title = next((l[3:] for l in block.splitlines() if l[3:4].isdigit()), "")
    query = "\n".join(l for l in block.splitlines() if not l.strip().startswith("--")).strip()
    if query:
        print(f"\n{title}")
        print(con.sql(query))
