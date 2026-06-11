#!/bin/bash
# Query Reality Sync costs from BigQuery billing export
# Run after data has populated and setup_billing_view.sh has been executed

PROJECT="project-07850c05-c54d-486b-80a"
DATASET="billing_export"

# Find the latest billing export table
TABLE=$(bq ls --format=json "$DATASET" 2>/dev/null | python3 -c "
import json,sys
try:
    data = json.load(sys.stdin)
    tables = [t.get('tableReference',{}).get('tableId','') for t in data if 'gcp_billing_export_resource' in t.get('tableReference',{}).get('tableId','')]
    if tables:
        print(sorted(tables)[-1])
except:
    pass
")

if [ -z "$TABLE" ]; then
    echo "ERROR: No billing export table found in ${PROJECT}:${DATASET}"
    echo "Run scripts/setup_billing_view.sh first once data arrives."
    exit 1
fi

echo "Using table: $TABLE"
echo ""

case "${1:-all}" in
  monthly)
    echo "=== Monthly Reality Sync Cost ==="
    bq query --use_legacy_sql=false "
      SELECT
        DATE_TRUNC(DATE(usage_start_time), MONTH) AS month,
        ROUND(SUM(cost), 2) AS total_cost,
        ROUND(SUM(credits), 2) AS total_credits,
        ROUND(SUM(cost) - SUM(credits), 2) AS net_cost
      FROM \`${PROJECT}.${DATASET}.${TABLE}\`
      WHERE EXISTS (SELECT 1 FROM UNNEST(labels) AS l WHERE l.key = 'app' AND l.value = 'realitysync')
      GROUP BY month
      ORDER BY month DESC
    "
    ;;
  daily)
    echo "=== Daily Reality Sync Cost (Last 30 Days) ==="
    bq query --use_legacy_sql=false "
      SELECT
        DATE(usage_start_time) AS day,
        ROUND(SUM(cost), 2) AS total_cost,
        ROUND(SUM(cost) - SUM(credits), 2) AS net_cost
      FROM \`${PROJECT}.${DATASET}.${TABLE}\`
      WHERE EXISTS (SELECT 1 FROM UNNEST(labels) AS l WHERE l.key = 'app' AND l.value = 'realitysync')
        AND DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
      GROUP BY day
      ORDER BY day DESC
    "
    ;;
  service)
    echo "=== Reality Sync Cost by Service ==="
    bq query --use_legacy_sql=false "
      SELECT
        service.description AS service,
        ROUND(SUM(cost), 2) AS total_cost,
        ROUND(SUM(cost) - SUM(credits), 2) AS net_cost
      FROM \`${PROJECT}.${DATASET}.${TABLE}\`
      WHERE EXISTS (SELECT 1 FROM UNNEST(labels) AS l WHERE l.key = 'app' AND l.value = 'realitysync')
      GROUP BY service
      ORDER BY net_cost DESC
    "
    ;;
  latest|current)
    echo "=== Current Month Reality Sync Cost ==="
    bq query --use_legacy_sql=false "
      SELECT
        service.description AS service,
        sku.description AS sku,
        ROUND(SUM(cost), 2) AS cost,
        ROUND(SUM(credits), 2) AS credits,
        ROUND(SUM(cost) - SUM(credits), 2) AS net_cost
      FROM \`${PROJECT}.${DATASET}.${TABLE}\`
      WHERE EXISTS (SELECT 1 FROM UNNEST(labels) AS l WHERE l.key = 'app' AND l.value = 'realitysync')
        AND DATE(usage_start_time) >= DATE_TRUNC(CURRENT_DATE(), MONTH)
      GROUP BY service, sku
      ORDER BY net_cost DESC
    "
    ;;
  forecast)
    echo "=== Reality Sync Cost Forecast (Trailing 12 Months) ==="
    bq query --use_legacy_sql=false "
      SELECT
        DATE_TRUNC(DATE(usage_start_time), MONTH) AS month,
        ROUND(SUM(cost), 2) AS total_cost,
        ROUND(SUM(cost) - SUM(credits), 2) AS net_cost
      FROM \`${PROJECT}.${DATASET}.${TABLE}\`
      WHERE EXISTS (SELECT 1 FROM UNNEST(labels) AS l WHERE l.key = 'app' AND l.value = 'realitysync')
        AND DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
      GROUP BY month
      ORDER BY month ASC
    "
    ;;
  all|*)
    echo "=== Reality Sync Cost Summary ==="
    bq query --use_legacy_sql=false "
      SELECT
        DATE_TRUNC(DATE(usage_start_time), MONTH) AS month,
        service.description AS service,
        ROUND(SUM(cost), 2) AS cost,
        ROUND(SUM(credits), 2) AS credits,
        ROUND(SUM(cost) - SUM(credits), 2) AS net_cost
      FROM \`${PROJECT}.${DATASET}.${TABLE}\`
      WHERE EXISTS (SELECT 1 FROM UNNEST(labels) AS l WHERE l.key = 'app' AND l.value = 'realitysync')
      GROUP BY month, service
      ORDER BY month DESC, net_cost DESC
      LIMIT 50
    "
    ;;
esac
