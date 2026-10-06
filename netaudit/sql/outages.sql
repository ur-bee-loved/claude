-- Every outage (consecutive minutes at 100% loss) per host
WITH base AS (
    SELECT * FROM RedeAudit
    WHERE (:audit IS NULL OR auditId = :audit)
      AND (:host  IS NULL OR host = :host)
      AND (:since IS NULL OR dateTime >= :since)
      AND (:until IS NULL OR dateTime <  :until)
),
flagged AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY auditId, host ORDER BY dateTime, id)
         - ROW_NUMBER() OVER (PARTITION BY auditId, host, loss_pct = 100 ORDER BY dateTime, id) AS island,
           ROW_NUMBER() OVER (PARTITION BY auditId, host ORDER BY dateTime DESC, id DESC) = 1 AS is_last
    FROM base
)
SELECT
    auditId,
    host,
    MIN(dateTime)                              AS start_utc,
    MAX(dateTime)                              AS end_utc,
    COUNT(*)                                   AS minutes,
    CASE WHEN MAX(is_last) THEN 'yes' ELSE '' END AS still_down_at_end
FROM flagged
WHERE loss_pct = 100
GROUP BY auditId, host, island
ORDER BY start_utc, host;
