set -euo pipefail

S3_PREFIX="s3://${CTORM_BUCKET}/cumulus-granules/${DUMP_SUBDIR}"
FAILED_SLICES_FILE="failed_slices_daily.tsv"

rm -f "$FAILED_SLICES_FILE"

while IFS=$'\t' read -r COLLECTION YYYYMMDD GRANULE_COUNT FILE_COUNT; do
  if [[ -z "${COLLECTION:-}" || ! "${YYYYMMDD:-}" =~ ^[0-9]{8}$ ]]; then
    echo "Skipping malformed slice row: collection=${COLLECTION:-<empty>} yyyymmdd=${YYYYMMDD:-<empty>}" >&2
    continue
  fi

  YYYYMM="${YYYYMMDD:0:6}"
  SAFE_COLLECTION=$(echo "$COLLECTION" | tr -c 'A-Za-z0-9._-' '_')
  S3_URI="${S3_PREFIX}/${SAFE_COLLECTION}/${YYYYMM}/${YYYYMMDD}.jsonl.gz"
  TMP_OUTPUT="$(mktemp "${SAFE_COLLECTION}.${YYYYMMDD}.XXXXXX.jsonl.gz")"

  echo "Exporting collection=${COLLECTION} yyyymmdd=${YYYYMMDD} expected_granules=${GRANULE_COUNT} expected_files=${FILE_COUNT}"
  echo "Destination: ${S3_URI}"
  echo "Temporary output: ${TMP_OUTPUT}"

  if ! PGOPTIONS="-c statement_timeout=${PG_STATEMENT_TIMEOUT:-0}" psql \
    --host="$PGHOST" \
    --port="${PGPORT:-5432}" \
    --username="$PGUSER" \
    --dbname="$PGDATABASE" \
    --quiet \
    --no-psqlrc \
    --set=ON_ERROR_STOP=1 \
    --set=collection="$COLLECTION" \
    --set=yyyymmdd="$YYYYMMDD" \
    --file=export-granules-slice-daily.sql \
    | gzip -c > "$TMP_OUTPUT"; then

    echo "FAILED query/gzip collection=${COLLECTION} yyyymmdd=${YYYYMMDD}; continuing with next slice" >&2
    printf '%s\t%s\t%s\t%s\n' "$COLLECTION" "$YYYYMMDD" "$GRANULE_COUNT" "$FILE_COUNT" >> "$FAILED_SLICES_FILE"
    rm -f "$TMP_OUTPUT"
    continue
  fi

  source ./refresh-ctorm-upload-role.sh

  if ! aws s3 cp "$TMP_OUTPUT" "$S3_URI"; then
    echo "FAILED upload collection=${COLLECTION} yyyymmdd=${YYYYMMDD}; continuing with next slice" >&2
    printf '%s\t%s\t%s\t%s\n' "$COLLECTION" "$YYYYMMDD" "$GRANULE_COUNT" "$FILE_COUNT" >> "$FAILED_SLICES_FILE"
    rm -f "$TMP_OUTPUT"
    continue
  fi

  rm -f "$TMP_OUTPUT"
  echo "Uploaded ${S3_URI}"

done < slices_daily.tsv

if [[ -s "$FAILED_SLICES_FILE" ]]; then
  source ./refresh-ctorm-upload-role.sh
  FAILED_SLICES_S3_URI="${S3_PREFIX}/failed_slices_daily.tsv"
  aws s3 cp "$FAILED_SLICES_FILE" "$FAILED_SLICES_S3_URI"
  echo "Some slices failed. Uploaded failure list to ${FAILED_SLICES_S3_URI}" >&2
else
  echo "All slices exported successfully."
fi
