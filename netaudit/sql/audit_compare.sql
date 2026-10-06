-- Compare audits: period, packet loss, clean and fully-down minutes, packet-weighted latency
WITH base AS (
    SELECT * FROM RedeAudit
    WHERE (:audit IS NULL OR auditId = :audit)
      AND (:host  IS NULL OR host = :host)
      AND (:since IS NULL OR dateTime >= :since)
      AND (:until IS NULL OR dateTime <  :until)
)
SELECT
    a.auditId,
    a.auditDate                                                          AS created_utc,
    MIN(b.dateTime)                                                      AS first_utc,
    MAX(b.dateTime)                                                      AS last_utc,
    COUNT(DISTINCT b.host)                                               AS hosts,
    COUNT(*)                                                             AS host_minutes,
    SUM(b.sent)                                                          AS pings_sent,
    ROUND(100.0 * (SUM(b.sent) - SUM(MIN(b.recv, b.sent))) / SUM(b.sent), 3) AS packet_loss_pct,
    ROUND(100.0 * SUM(b.loss_pct = 0) / COUNT(*), 2)                     AS clean_minutes_pct,
    SUM(b.loss_pct = 100)                                                AS down_minutes,
    ROUND(SUM(b.avg_ms * b.recv) / SUM(CASE WHEN b.avg_ms IS NOT NULL THEN b.recv END), 2) AS mean_rtt_ms,
    ROUND(MAX(b.max_ms), 2)                                              AS worst_rtt_ms
FROM Audits a
JOIN base b ON b.auditId = a.auditId
GROUP BY a.auditId
ORDER BY a.auditDate;
