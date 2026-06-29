
set -euo pipefail


#ANTPAT',
#BFPQ',
#CORNER_REFL',
#DCOP',
#DC_RADAR',
#DSG_STATIC',
#EA_L0B_L_CRSD',
#EA_L0B_L_RRSD',
#EA_L1_L_RIFG',
#EA_L1_L_ROFF',
#EA_L1_L_RSLC',
#EA_L1_L_RUNW',--
#EA_L2_L_GCOV',
#EA_L2_L_GOFF',
#EA_L2_L_GSLC',
#EA_L2_L_GUNW',
#EA_L3_L_SME2',
#FOE',
#FRP',
#FT_PARAM',
#FT_WAVEFORM',
#LRCLK_UTC',
#L_CHAN_DATA',
#MOE',
#NISAR_DEM_TIF',
#NISAR_DEM_VRT',
#NISAR_L0A_RRST_BETA_V1',
#NISAR_L0B_CRSD_BETA_V1',
#NISAR_L0B_RRSD_BETA_V1',
#NISAR_L1_RIFG_BETA_V1',
#NISAR_L1_ROFF_BETA_V1',
#NISAR_L1_RSLC_BETA_V1',
#NISAR_L1_RUNW_BETA_V1',
#NISAR_L2_GCOV_BETA_V1',
#NISAR_L2_GOFF_BETA_V1',
#NISAR_L2_GSLC_BETA_V1',
#NISAR_L2_GUNW_BETA_V1',
#NISAR_L3_SME2_BETA_V1',
#NISAR_VWC',
#NISAR_WATERMASK_TIF',
#NISAR_WATERMASK_VRT',
#NOE',
#NRP',
#OROST',
#PA_L0B_L_RRSD',
#POE',
#PRP',
#STUF',
#TEC',
#TFDB',
#UR_L0B_L_RRSD',
# Opera collections:
#COLLECTION="OPERA_L2_CSLC-S1_V1"
#COLLECTION="OPERA_L2_RTC-S1_V1"
#COLLECTION="OPERA_L3_DISP-S1_V1"
#COLLECTION="OPERA_L3_DIST-ALERT-S1_V1"
#COLLECTION="OPERA_L4_TROPO-ZENITH_V1"

echo "SLICES_S3_URI: ${SLICES_S3_URI}"
echo "COLLECTION: ${COLLECTION}"

if [[ -n "${SLICES_S3_URI:-}" ]]; then
  echo "SLICES_S3_URI is specified: ${SLICES_S3_URI}"
  echo "Downloading specified slices file instead of querying database..."
  source ./refresh-ctorm-upload-role.sh
  aws s3 cp "${SLICES_S3_URI}" slices_daily.tsv
else
  # Generate slices TSV file
  echo "SLICES_S3_URI not set. Going to run a big query now..."
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
    --set=collection="$COLLECTION" \
    --file=generate-slices-daily.sql \
    > slices_daily.tsv

  source ./refresh-ctorm-upload-role.sh

  # Upload slices TSV file to S3 for archive purposes.
  SLICES_S3_UPLOAD_URI="s3://${CTORM_BUCKET}/cumulus-granules/${DUMP_SUBDIR}/slices_daily-${COLLECTION}-${CODEBUILD_BUILD_NUMBER}.tsv"
  aws s3 cp slices_daily.tsv "${SLICES_S3_UPLOAD_URI}"
  echo "Uploaded ${SLICES_S3_UPLOAD_URI}"
fi
