select
    polygon_id,
    qa_status
from {{ ref('stg_ml_polygons') }}
where qa_status not in ('pending', 'validated', 'low_confidence', 'corrected', 'escalated')
