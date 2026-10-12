#!/bin/sh
set -eu

aws_local() { aws --endpoint-url http://floci:4566 "$@"; }

# Floci emits host-facing URLs; this runner needs the container-facing hostname.
queue_url() {
  url=$(aws_local sqs create-queue --queue-name "$1" --query QueueUrl --output text)
  printf 'http://floci:4566/%s\n' "${url#*://*/}"
}

queue_arn() {
  aws_local sqs get-queue-attributes --queue-url "$1" \
    --attribute-names QueueArn --query Attributes.QueueArn --output text
}

bus=telelink-local
exists=$(aws_local events list-event-buses --query "length(EventBuses[?Name=='$bus'])" --output json)
if [ "$exists" -eq 0 ]; then
  aws_local events create-event-bus --name "$bus" > /dev/null
fi

delivery_url=$(queue_url telelink-local-event-delivery-dlq)
delivery_arn=$(queue_arn "$delivery_url")
aws_local sqs set-queue-attributes --queue-url "$delivery_url" \
  --attributes '{"MessageRetentionPeriod":"1209600"}'

for consumer in scheduling fulfilment document notification; do
  dlq_url=$(queue_url "telelink-local-$consumer-dlq")
  dlq_arn=$(queue_arn "$dlq_url")
  url=$(queue_url "telelink-local-$consumer")
  arn=$(queue_arn "$url")
  rule_arn=$(aws_local events put-rule --event-bus "$bus" \
    --name "$consumer-events" --state ENABLED \
    --event-pattern "file:///bootstrap/patterns/$consumer.json" \
    --query RuleArn --output text)
  printf '%s\n' "$rule_arn" > "/tmp/$consumer-rule-arn"

  cat > /tmp/queue-attributes.json <<EOF
{
  "VisibilityTimeout": "30",
  "MessageRetentionPeriod": "345600",
  "RedrivePolicy": "{\"deadLetterTargetArn\":\"$dlq_arn\",\"maxReceiveCount\":3}",
  "Policy": "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"events.amazonaws.com\"},\"Action\":\"sqs:SendMessage\",\"Resource\":\"$arn\",\"Condition\":{\"ArnEquals\":{\"aws:SourceArn\":\"$rule_arn\"}}}]}"
}
EOF
  aws_local sqs set-queue-attributes --queue-url "$url" \
    --attributes file:///tmp/queue-attributes.json

  cat > /tmp/dlq-attributes.json <<EOF
{
  "MessageRetentionPeriod": "1209600",
  "RedriveAllowPolicy": "{\"redrivePermission\":\"byQueue\",\"sourceQueueArns\":[\"$arn\"]}"
}
EOF
  aws_local sqs set-queue-attributes --queue-url "$dlq_url" \
    --attributes file:///tmp/dlq-attributes.json

  cat > /tmp/targets.json <<EOF
[{
  "Id": "$consumer",
  "Arn": "$arn",
  "DeadLetterConfig": {"Arn": "$delivery_arn"},
  "RetryPolicy": {"MaximumRetryAttempts": 3, "MaximumEventAgeInSeconds": 3600}
}]
EOF
  failed=$(aws_local events put-targets --event-bus "$bus" \
    --rule "$consumer-events" --targets file:///tmp/targets.json \
    --query FailedEntryCount --output text)
  if [ "$failed" -ne 0 ]; then
    printf 'Failed to attach target: %s\n' "$consumer" >&2
    exit 1
  fi
  printf 'Consumer route ready: %s\n' "$consumer"
done

cat > /tmp/delivery-dlq-policy.json <<EOF
{
  "Policy": "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"events.amazonaws.com\"},\"Action\":\"sqs:SendMessage\",\"Resource\":\"$delivery_arn\",\"Condition\":{\"ArnEquals\":{\"aws:SourceArn\":[\"$(cat /tmp/scheduling-rule-arn)\",\"$(cat /tmp/fulfilment-rule-arn)\",\"$(cat /tmp/document-rule-arn)\",\"$(cat /tmp/notification-rule-arn)\"]}}}]}"
}
EOF
aws_local sqs set-queue-attributes --queue-url "$delivery_url" \
  --attributes file:///tmp/delivery-dlq-policy.json
printf 'Event bus ready: %s\n' "$bus"
