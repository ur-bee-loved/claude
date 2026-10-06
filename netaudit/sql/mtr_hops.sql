-- mtr per target and hop: runs, mean loss, mean and worst latency (needs mtr data)
SELECT
    target,
    hop,
    GROUP_CONCAT(DISTINCT ip)                  AS ips,
    COUNT(*)                                   AS runs,
    ROUND(AVG(loss_pct), 2)                    AS mean_loss_pct,
    ROUND(AVG(avg_ms), 2)                      AS mean_avg_ms,
    ROUND(MAX(worst_ms), 2)                    AS worst_ms
FROM MtrAudit
WHERE (:audit IS NULL OR auditId = :audit)
  AND (:host  IS NULL OR target = :host)
  AND (:since IS NULL OR dateTime >= :since)
  AND (:until IS NULL OR dateTime <  :until)
GROUP BY target, hop
ORDER BY target, hop;
