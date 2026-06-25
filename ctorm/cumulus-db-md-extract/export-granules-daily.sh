set -euo pipefail

S3_PREFIX="s3://${CTORM_BUCKET}/cumulus-granules/${DUMP_SUBDIR}"
FAILED_SLICES_FILE="failed_slices_daily.tsv"

rm -f "$FAILED_SLICES_FILE"

echo "Statement timeout: "
psql \
    --host="$PGHOST" \
    --port="${PGPORT:-5432}" \
    --username="$PGUSER" \
    --dbname="$PGDATABASE" \
    --no-psqlrc \
    -c "SHOW statement_timeout;"



while IFS=$'\t' read -r COLLECTION YYYYMMDD GRANULE_COUNT FILE_COUNT; do
  if [[ -z "${COLLECTION:-}" || ! "${YYYYMMDD:-}" =~ ^[0-9]{8}$ ]]; then
    echo "Skipping malformed slice row: collection=${COLLECTION:-<empty>} yyyymmdd=${YYYYMMDD:-<empty>}" >&2
    continue
  fi

  YYYYMM="${YYYYMMDD:0:6}"
  SAFE_COLLECTION=$(echo "$COLLECTION" | tr -c 'A-Za-z0-9._-' '_')
  S3_URI="${S3_PREFIX}/${SAFE_COLLECTION}/${YYYYMM}/${YYYYMMDD}.jsonl.gz"

  echo "Exporting collection=${COLLECTION} yyyymmdd=${YYYYMMDD} expected_granules=${GRANULE_COUNT} expected_files=${FILE_COUNT}"
  echo "Destination: ${S3_URI}"

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
    | gzip -c \
    | aws s3 cp - "$S3_URI"; then

    echo "FAILED collection=${COLLECTION} yyyymmdd=${YYYYMMDD}; continuing with next slice" >&2
    printf '%s\t%s\t%s\t%s\n' "$COLLECTION" "$YYYYMMDD" "$GRANULE_COUNT" "$FILE_COUNT" >> "$FAILED_SLICES_FILE"
    continue
  fi

  echo "Uploaded ${S3_URI}"

done < slices_daily.tsv

if [[ -s "$FAILED_SLICES_FILE" ]]; then
  FAILED_SLICES_S3_URI="${S3_PREFIX}/failed_slices_daily.tsv"
  aws s3 cp "$FAILED_SLICES_FILE" "$FAILED_SLICES_S3_URI"
  echo "Some slices failed. Uploaded failure list to ${FAILED_SLICES_S3_URI}" >&2
else
  echo "All slices exported successfully."
fi
