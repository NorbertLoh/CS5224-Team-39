#!/bin/sh
set -eu

aws_local() { aws --endpoint-url http://floci:4566 "$@"; }

pool_name=telelink-local
count=$(aws_local cognito-idp list-user-pools --max-results 60 \
  --query "length(UserPools[?Name=='$pool_name'])" --output json)
case "$count" in
  0) pool_id=$(aws_local cognito-idp create-user-pool --pool-name "$pool_name" \
       --admin-create-user-config AllowAdminCreateUserOnly=true \
       --mfa-configuration OFF --query UserPool.Id --output text) ;;
  1) pool_id=$(aws_local cognito-idp list-user-pools --max-results 60 \
       --query "UserPools[?Name=='$pool_name'].Id" --output text) ;;
  *) printf 'Multiple pools named %s; resolve before bootstrap.\n' "$pool_name" >&2; exit 1 ;;
esac

client_name=telelink-web
count=$(aws_local cognito-idp list-user-pool-clients --user-pool-id "$pool_id" \
  --max-results 60 --query "length(UserPoolClients[?ClientName=='$client_name'])" --output json)
case "$count" in
  0) client_id=$(aws_local cognito-idp create-user-pool-client \
       --user-pool-id "$pool_id" --client-name "$client_name" --no-generate-secret \
       --query UserPoolClient.ClientId --output text) ;;
  1) client_id=$(aws_local cognito-idp list-user-pool-clients --user-pool-id "$pool_id" \
       --max-results 60 --query "UserPoolClients[?ClientName=='$client_name'].ClientId" --output text) ;;
  *) printf 'Multiple clients named %s; resolve before bootstrap.\n' "$client_name" >&2; exit 1 ;;
esac

secret=$(aws_local cognito-idp describe-user-pool-client --user-pool-id "$pool_id" \
  --client-id "$client_id" --query UserPoolClient.ClientSecret --output text)
if [ "$secret" != None ] && [ -n "$secret" ]; then
  printf 'The existing SPA client has a secret; a public client is required.\n' >&2
  exit 1
fi
aws_local cognito-idp update-user-pool-client --user-pool-id "$pool_id" \
  --client-id "$client_id" --client-name "$client_name" \
  --supported-identity-providers COGNITO \
  --allowed-o-auth-flows-user-pool-client --allowed-o-auth-flows code \
  --allowed-o-auth-scopes openid email profile \
  --callback-urls "$COGNITO_CALLBACK_URL" http://127.0.0.1:5173/auth/callback \
  --logout-urls "$COGNITO_LOGOUT_URL" http://127.0.0.1:5173/ \
  --explicit-auth-flows ALLOW_REFRESH_TOKEN_AUTH \
  --prevent-user-existence-errors ENABLED > /dev/null

for role in patient doctor clinic_admin platform_admin; do
  count=$(aws_local cognito-idp list-groups --user-pool-id "$pool_id" \
    --query "length(Groups[?GroupName=='$role'])" --output json)
  if [ "$count" -eq 0 ]; then
    aws_local cognito-idp create-group --user-pool-id "$pool_id" \
      --group-name "$role" --description 'Synthetic local role fixture' > /dev/null
  fi
  case "$role" in
    clinic_admin) username=clinic@example.test ;;
    platform_admin) username=platform@example.test ;;
    *) username="$role@example.test" ;;
  esac
  count=$(aws_local cognito-idp list-users --user-pool-id "$pool_id" \
    --filter "username = \"$username\"" --query 'length(Users)' --output json)
  if [ "$count" -eq 0 ]; then
    aws_local cognito-idp admin-create-user --user-pool-id "$pool_id" \
      --username "$username" --message-action SUPPRESS \
      --temporary-password 'LocalDemo123!' \
      --user-attributes "Name=email,Value=$username" Name=email_verified,Value=true > /dev/null
  fi
  status=$(aws_local cognito-idp admin-get-user --user-pool-id "$pool_id" \
    --username "$username" --query UserStatus --output text)
  if [ "$status" = FORCE_CHANGE_PASSWORD ]; then
    aws_local cognito-idp admin-set-user-password --user-pool-id "$pool_id" \
      --username "$username" --password 'LocalDemo123!' --permanent > /dev/null
  fi
  aws_local cognito-idp admin-add-user-to-group --user-pool-id "$pool_id" \
    --username "$username" --group-name "$role"
  printf 'Demo user ready: %s (%s)\n' "$username" "$role"
done

printf 'COGNITO_USER_POOL_ID=%s\nCOGNITO_CLIENT_ID=%s\nCOGNITO_ISSUER=%s/%s\n' \
  "$pool_id" "$client_id" "$COGNITO_BASE_URL" "$pool_id"
