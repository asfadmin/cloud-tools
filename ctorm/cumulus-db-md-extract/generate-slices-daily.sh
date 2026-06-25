
set -euo pipefail


S3_URI="s3://${CTORM_BUCKET}/cumulus-granules/${DUMP_SUBDIR}"

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
    AND c.name in (
      'ANTPAT',
      'BFPQ',
      'CORNER_REFL',
      'DCOP',
      'DC_RADAR',
      'DSG_STATIC',
      'EA_L0B_L_CRSD',
      'EA_L0B_L_RRSD',
      'EA_L1_L_RIFG',
      'EA_L1_L_ROFF',
      'EA_L1_L_RSLC',
      'EA_L1_L_RUNW',
      'EA_L2_L_GCOV',
      'EA_L2_L_GOFF',
      'EA_L2_L_GSLC',
      'EA_L2_L_GUNW',
      'EA_L3_L_SME2',
      'FOE',
      'FRP',
      'FT_PARAM',
      'FT_WAVEFORM',
      'LRCLK_UTC',
      'L_CHAN_DATA',
      'MOE',
      'NISAR_DEM_TIF',
      'NISAR_DEM_VRT',
      'NISAR_L0A_RRST_BETA_V1',
      'NISAR_L0B_CRSD_BETA_V1',
      'NISAR_L0B_RRSD_BETA_V1',
      'NISAR_L1_RIFG_BETA_V1',
      'NISAR_L1_ROFF_BETA_V1',
      'NISAR_L1_RSLC_BETA_V1',
      'NISAR_L1_RUNW_BETA_V1',
      'NISAR_L2_GCOV_BETA_V1',
      'NISAR_L2_GOFF_BETA_V1',
      'NISAR_L2_GSLC_BETA_V1',
      'NISAR_L2_GUNW_BETA_V1',
      'NISAR_L3_SME2_BETA_V1',
      'NISAR_VWC',
      'NISAR_WATERMASK_TIF',
      'NISAR_WATERMASK_VRT',
      'NOE',
      'NRP',
      'OROST',
      'PA_L0B_L_RRSD',
      'POE',
      'PRP',
      'STUF',
      'TEC',
      'TFDB',
      'UR_L0B_L_RRSD',

      'OPERA_L2_CSLC-S1_V1',
      'OPERA_L2_RTC-S1_V1',
      'OPERA_L3_DISP-S1_V1',
      'OPERA_L3_DIST-ALERT-S1_V1',
      'OPERA_L4_TROPO-ZENITH_V1'
    )
    GROUP BY
      c.name,
      to_char(g.beginning_date_time AT TIME ZONE 'UTC', 'YYYYMMDD')
    ORDER BY
      c.name,
      to_char(g.beginning_date_time AT TIME ZONE 'UTC', 'YYYYMMDD');
  " > slices_daily.tsv
  aws s3 cp slices_daily.tsv "$S3_URI/"
