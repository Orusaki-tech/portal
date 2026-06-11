#!/bin/bash
# Creates a BigQuery view filtering Reality Sync costs by app:realitysync label
# Run this after the billing export tables appear in billing_export dataset

PROJECT="project-07850c05-c54d-486b-80a"
DATASET="billing_export"

echo "Looking for billing export tables in ${PROJECT}:${DATASET}..."
TABLES=$(bq ls --format=json "${DATASET}" 2>/dev/null | python3 -c "
import json,sys
try:
    data = json.load(sys.stdin)
    for t in data:
        tid = t.get('tableReference',{}).get('tableId','')
        if 'gcp_billing_export_resource' in tid:
            print(tid)
except:
    pass
")

if [ -z "$TABLES" ]; then
    echo "No billing export tables found yet. Check back later."
    echo "Expected table pattern: gcp_billing_export_resource_v1_*"
    exit 1
fi

TABLE_ID=$(echo "$TABLES" | head -1)
echo "Found table: ${TABLE_ID}"

VIEW_ID="realitysync_costs"
echo "Creating view: ${VIEW_ID}"

bq mk \
  --use_legacy_sql=false \
  --description="Reality Sync costs filtered by app=realitysync label" \
  --view="
    SELECT *
    FROM \`${PROJECT}.${DATASET}.${TABLE_ID}\`
    WHERE EXISTS (
      SELECT 1 FROM UNNEST(labels) AS l
      WHERE l.key = 'app' AND l.value = 'realitysync'
    )
  " \
  "${PROJECT}:${DATASET}.${VIEW_ID}"

echo "View created: ${PROJECT}:${DATASET}.${VIEW_ID}"
echo ""
echo "Query it with:"
echo "  bq query --use_legacy_sql=false 'SELECT * FROM \`${PROJECT}.${DATASET}.${VIEW_ID}\` LIMIT 10'"
