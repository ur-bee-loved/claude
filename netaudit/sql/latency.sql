-- Latency per host: percentiles of per-minute averages, packet-weighted mean, spread, spike minutes (:spike_ms, default 500)
WITH base AS (
    SELECT * FROM RedeAudit
    WHERE avg_ms IS NOT NULL
      AND (:audit IS NULL OR auditId = :audit)
      AND (:host  IS NULL OR host = :host)
      AND (:since IS NULL OR dateTime >= :since)
      AND (:until IS NULL OR dateTime <  :until)
),
ranked AS (
    SELECT host, min_ms, avg_ms, max_ms, recv,
           ROW_NUMBER() OVER (PARTITION BY host ORDER BY avg_ms) AS rn,
           COUNT(*)     OVER (PARTITION BY host)                 AS n
    FROM base
)
SELECT
    host,
    COUNT(*)                                                     AS minutes,
    ROUND(MIN(min_ms), 2)                                        AS best_ms,
    ROUND(MIN(CASE WHEN rn * 100 >= n * 50 THEN avg_ms END), 2)  AS p50_ms,
    ROUND(MIN(CASE WHEN rn * 100 >= n * 95 THEN avg_ms END), 2)  AS p95_ms,
    ROUND(MIN(CASE WHEN rn * 100 >= n * 99 THEN avg_ms END), 2)  AS p99_ms,
    ROUND(SUM(avg_ms * recv) / SUM(recv), 2)                     AS mean_ms,
    ROUND(sqrt(MAX(0, (SUM(avg_ms * avg_ms) - SUM(avg_ms) * SUM(avg_ms) / COUNT(*)) / (COUNT(*) - 1))), 2) AS sd_ms,
    ROUND(MAX(max_ms), 2)                                        AS worst_ms,
    SUM(max_ms >= COALESCE(:spike_ms, 500))                      AS spike_minutes
FROM ranked
GROUP BY host
ORDER BY p95_ms DESC;
