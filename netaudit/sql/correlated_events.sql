-- Minutes where at least :min_share % of hosts (default 50) lost packets or exceeded :spike_ms (default 500) at once; points to a cause near the monitoring machine
WITH base AS (
    SELECT * FROM RedeAudit
    WHERE (:audit IS NULL OR auditId = :audit)
      AND (:host  IS NULL OR host = :host)
      AND (:since IS NULL OR dateTime >= :since)
      AND (:until IS NULL OR dateTime <  :until)
),
per_minute AS (
    SELECT
        auditId,
        dateTime,
        COUNT(*)                                                         AS hosts,
        SUM(loss_pct > 0)                                                AS with_loss,
        SUM(max_ms >= COALESCE(:spike_ms, 500))                          AS with_spike,
        SUM(loss_pct > 0 OR max_ms >= COALESCE(:spike_ms, 500))          AS affected,
        GROUP_CONCAT(CASE WHEN loss_pct > 0 OR max_ms >= COALESCE(:spike_ms, 500) THEN host END, ' ') AS affected_hosts
    FROM base
    GROUP BY auditId, dateTime
)
SELECT
    auditId,
    dateTime AS time_utc,
    hosts,
    affected,
    with_loss,
    with_spike,
    affected_hosts
FROM per_minute
WHERE affected > 1
  AND affected * 100 >= hosts * COALESCE(:min_share, 50)
ORDER BY dateTime;
