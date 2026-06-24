set -euo pipefail

S3_PREFIX="s3://${CTORM_BUCKET}/cumulus-granules/${DUMP_SUBDIR}"

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

  psql \
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
    | awk -v label="${COLLECTION} ${YYYYMMDD}" '
        {
          print;
          count++;
          if (count % 1000 == 0) {
            printf("[%s] exported %d JSONL rows\n", label, count) > "/dev/stderr";
            fflush("/dev/stderr");
          }
        }
        END {
          printf("[%s] export complete: %d JSONL rows\n", label, count) > "/dev/stderr";
        }
      ' \
    | gzip -c \
    | aws --profile=ctorm s3 cp - "$S3_URI"

  echo "Uploaded ${S3_URI}"

done < slices_daily.tsv
