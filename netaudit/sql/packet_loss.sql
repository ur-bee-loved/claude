-- Packet loss per host: packet-weighted loss, minutes with partial loss vs fully down, worst minute
WITH base AS (
    SELECT * FROM RedeAudit
    WHERE (:audit IS NULL OR auditId = :audit)
      AND (:host  IS NULL OR host = :host)
      AND (:since IS NULL OR dateTime >= :since)
      AND (:until IS NULL OR dateTime <  :until)
)
SELECT
    host,
    COUNT(*)                                                     AS minutes,
    SUM(sent)                                                    AS pings_sent,
    SUM(sent) - SUM(MIN(recv, sent))                             AS pings_lost,
    ROUND(100.0 * (SUM(sent) - SUM(MIN(recv, sent))) / SUM(sent), 3) AS packet_loss_pct,
    SUM(loss_pct > 0)                                            AS lossy_minutes,
    ROUND(100.0 * SUM(loss_pct > 0) / COUNT(*), 2)               AS lossy_minutes_pct,
    SUM(loss_pct > 0 AND loss_pct < 100)                         AS partial_loss_minutes,
    SUM(loss_pct = 100)                                          AS down_minutes,
    MAX(loss_pct)                                                AS worst_minute_loss_pct
FROM base
GROUP BY host
ORDER BY packet_loss_pct DESC;
