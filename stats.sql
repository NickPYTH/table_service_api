SELECT
    date,
    COUNT(DISTINCT user_id) AS unique_users_per_date
FROM tables_useronlinehistory
GROUP BY date
ORDER BY date;