psql \
  --host="$PGHOST" \
  --port="${PGPORT:-5432}" \
  --username="$PGUSER" \
  --dbname="$PGDATABASE" \
  --quiet \
  --no-psqlrc \
  --tuples-only \
  --no-align \
  --field-separator $'\t' \
  --set=ON_ERROR_STOP=1 \
  --command "
    SELECT
      c.name,
      to_char(g.beginning_date_time AT TIME ZONE 'UTC', 'YYYYMMDD') AS yyyymmdd,
      count(DISTINCT g.cumulus_id) AS granule_count,
      count(f.cumulus_id) AS file_count
    FROM public.granules g
    JOIN public.collections c
      ON c.cumulus_id = g.collection_cumulus_id
    JOIN public.files f
      ON f.granule_cumulus_id = g.cumulus_id
     AND f.checksum_value IS NOT NULL
    WHERE g.status = 'completed'
    GROUP BY
      c.name,
      to_char(g.beginning_date_time AT TIME ZONE 'UTC', 'YYYYMMDD')
    ORDER BY
      c.name,
      to_char(g.beginning_date_time AT TIME ZONE 'UTC', 'YYYYMMDD');
  " > slices_daily.tsv
