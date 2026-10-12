#!/bin/sh
set -eu

# Always target the local Compose service, using the runner's dummy credentials.
aws_local() {
  aws --endpoint-url http://floci:4566 "$@"
}

bucket=telelink-local-documents
exists=$(aws_local s3api list-buckets --query "length(Buckets[?Name=='$bucket'])" --output json)
if [ "$exists" -eq 0 ]; then
  if [ "$AWS_DEFAULT_REGION" = us-east-1 ]; then
    aws_local s3api create-bucket --bucket "$bucket" > /dev/null
  else
    aws_local s3api create-bucket --bucket "$bucket" \
      --create-bucket-configuration "LocationConstraint=$AWS_DEFAULT_REGION" > /dev/null
  fi
fi

aws_local s3api put-public-access-block --bucket "$bucket" \
  --public-access-block-configuration \
  'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'
printf 'Bucket ready: %s\n' "$bucket"

seed_secret() {
  exists=$(aws_local secretsmanager list-secrets \
    --query "length(SecretList[?Name=='$1'])" --output json)
  if [ "$exists" -eq 0 ]; then
    aws_local secretsmanager create-secret --name "$1" \
      --description 'Synthetic local development values; not provider credentials.' \
      --secret-string "$2" > /dev/null
  fi
  printf 'Secret ready: %s\n' "$1"
}

seed_secret telelink/local/stripe \
  '{"api_key":"synthetic-stripe-key","webhook_secret":"synthetic-stripe-webhook-secret"}'
seed_secret telelink/local/lalamove \
  '{"api_key":"synthetic-lalamove-key","api_secret":"synthetic-lalamove-secret"}'

/bin/sh /bootstrap/events.sh
/bin/sh /bootstrap/cognito.sh
