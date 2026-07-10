\pset tuples_only on
\pset format unaligned
\pset pager off

WITH export_rows AS (
  SELECT
    g.granule_id,
    c.name AS collection,
    to_char(g.beginning_date_time AT TIME ZONE 'UTC', 'YYYYMM') AS yyyymm,
    to_char(
      g.beginning_date_time AT TIME ZONE 'UTC',
      'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
    ) AS beginning_date_time,
    jsonb_agg(
      jsonb_build_object(
        'name', f.file_name,
        'type', f.type,
        'uri', 's3://' || f.bucket || '/' || f.key,
        'size', f.file_size,
        'checksum', f.checksum_value,
        'checksumType', 'md5'
      )
      ORDER BY f.file_name
    ) AS files
  FROM public.granules g
  JOIN public.collections c
    ON c.cumulus_id = g.collection_cumulus_id
  JOIN public.files f
    ON f.granule_cumulus_id = g.cumulus_id
   AND f.checksum_value IS NOT NULL
  WHERE g.status = 'completed'
    AND c.name = :'collection'

    AND g.beginning_date_time >= to_date(:'yyyymmdd', 'YYYYMMDD')
    AND g.beginning_date_time < (
      to_date(:'yyyymmdd', 'YYYYMMDD') + interval '1 day'
    ) AT TIME ZONE 'UTC'
  GROUP BY
    g.granule_id,
    c.name,
    to_char(g.beginning_date_time AT TIME ZONE 'UTC', 'YYYYMM'),
    to_char(
      g.beginning_date_time AT TIME ZONE 'UTC',
      'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
    )
)
SELECT jsonb_strip_nulls(
  jsonb_build_object(
    'pk', collection || '#' || yyyymm,
    'sk', beginning_date_time || '#' || granule_id,

    'gsi1pk', granule_id,
    'gsi1sk', collection || '#' || yyyymm,

    'collection', collection,
    'yyyymm', yyyymm,
    'beginning_date_time', beginning_date_time,
    'granule_id', granule_id,
    'load_test_count', 0,

    'n', granule_id,
    'c', collection,
    'cv', '1',
    'f', files
  )
)
FROM export_rows
ORDER BY beginning_date_time, granule_id;
