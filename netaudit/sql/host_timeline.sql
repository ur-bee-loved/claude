-- Every report of one host over time (needs --host)
-- requires: host
SELECT
    auditId,
    dateTime AS time_utc,
    sent,
    recv,
    loss_pct,
    min_ms,
    avg_ms,
    max_ms
FROM RedeAudit
WHERE host = :host
  AND (:audit IS NULL OR auditId = :audit)
  AND (:since IS NULL OR dateTime >= :since)
  AND (:until IS NULL OR dateTime <  :until)
ORDER BY dateTime, id;
