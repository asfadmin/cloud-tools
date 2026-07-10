set -euo pipefail



S3_URI_COPYTEST="s3://${CTORM_BUCKET}/cumulus-granules/${DUMP_SUBDIR}"
echo "Failing fast if we can't write to ${S3_URI_COPYTEST}..."
touch ./test-s3-write.txt
source ./refresh-ctorm-upload-role.sh
aws s3 cp ./test-s3-write.txt "${S3_URI_COPYTEST}/test-s3-write-${CODEBUILD_BUILD_NUMBER}.txt"
rm ./test-s3-write.txt
