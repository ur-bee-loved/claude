-- Availability per host: minutes up (not 100% loss), clean minutes, packets delivered, outages
WITH base AS (
    SELECT * FROM RedeAudit
    WHERE (:audit IS NULL OR auditId = :audit)
      AND (:host  IS NULL OR host = :host)
      AND (:since IS NULL OR dateTime >= :since)
      AND (:until IS NULL OR dateTime <  :until)
),
flagged AS (
    SELECT *,
           loss_pct = 100 AS down,
           ROW_NUMBER() OVER (PARTITION BY auditId, host ORDER BY dateTime, id)
         - ROW_NUMBER() OVER (PARTITION BY auditId, host, loss_pct = 100 ORDER BY dateTime, id) AS island
    FROM base
),
outages AS (
    SELECT auditId, host, island, COUNT(*) AS len
    FROM flagged
    WHERE down
    GROUP BY auditId, host, island
)
SELECT
    f.host,
    COUNT(*)                                                     AS minutes,
    ROUND(100.0 * SUM(NOT f.down) / COUNT(*), 2)                 AS up_minutes_pct,
    ROUND(100.0 * SUM(f.loss_pct = 0) / COUNT(*), 2)             AS clean_minutes_pct,
    ROUND(100.0 * SUM(MIN(f.recv, f.sent)) / SUM(f.sent), 3)     AS delivery_pct,
    SUM(f.down)                                                  AS down_minutes,
    (SELECT COUNT(*) FROM outages o WHERE o.host = f.host)       AS outages,
    COALESCE((SELECT MAX(len) FROM outages o WHERE o.host = f.host), 0) AS longest_outage_min
FROM flagged f
GROUP BY f.host
ORDER BY up_minutes_pct, delivery_pct;
