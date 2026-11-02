-- Reporting queries on outputs/portfolio.duckdb (run them with: python src/run_sql.py)

-- 1. Portfolio totals: generation, settlement and net cost per MWh
SELECT
    project,
    ROUND(SUM(actual_generation_mwh) / 1000, 1)                         AS generation_gwh,
    ROUND(SUM(actual_settlement_eur) / 1e6, 2)                          AS settlement_eur_m,
    ROUND(-SUM(actual_settlement_eur) / SUM(actual_generation_mwh), 2)  AS net_cost_eur_per_mwh
FROM monthly_report
GROUP BY project
ORDER BY project;

-- 2. Months where generation missed budget by more than 10%
SELECT
    project,
    month,
    ROUND(actual_generation_mwh, 0)                                   AS actual_mwh,
    ROUND(forecast_generation_mwh, 0)                                 AS budget_mwh,
    ROUND(100 * (actual_generation_mwh / forecast_generation_mwh - 1), 1) AS diff_pct
FROM monthly_report
WHERE ABS(actual_generation_mwh / forecast_generation_mwh - 1) > 0.10
ORDER BY ABS(actual_generation_mwh / forecast_generation_mwh - 1) DESC;

-- 3. Settlement variance bridge: budget -> volume effect -> price effect -> actual
SELECT
    project,
    ROUND(SUM(forecast_settlement_eur) / 1e6, 2) AS budget_eur_m,
    ROUND(SUM(volume_variance_eur) / 1e6, 2)     AS volume_effect_eur_m,
    ROUND(SUM(price_variance_eur) / 1e6, 2)      AS price_effect_eur_m,
    ROUND(SUM(actual_settlement_eur) / 1e6, 2)   AS actual_eur_m
FROM monthly_report
GROUP BY project;

-- 4. Hours with negative day-ahead prices and the generation exposed to them
SELECT
    project,
    COUNT(*)                          AS negative_price_hours,
    ROUND(SUM(generation_mwh), 0)     AS generation_in_those_hours_mwh,
    ROUND(SUM(settlement_eur) / 1e3, 1) AS settlement_in_those_hours_eur_k
FROM hourly
WHERE year = 2020 AND price_eur_mwh < 0
GROUP BY project;

-- 5. Invoice lines that need review
SELECT project, month, ROUND(100 * volume_diff_pct, 2) AS volume_diff_pct,
       ROUND(settlement_diff_eur, 0) AS settlement_diff_eur
FROM invoice_reconciliation
WHERE flag = 'REVIEW';
