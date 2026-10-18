# X05 Lalamove sandbox feasibility spike

Completed in merged PR #167; issue #166 closed. Verified by NorbertLoh.

Scope: isolated SG sandbox quotation, order, status and callback verification.
No application delivery or payment integration is implemented by this spike.
Credentials belong only in ignored `services/fulfilment/.env`.

## Setup and reproduction

Node.js 24, with built-in APIs only; no npm install or service runtime changes.
Fill the ignored `services/fulfilment/.env` with sandbox credentials:

```dotenv
LALAMOVE_API_KEY=pk_test_REPLACE_LOCALLY
LALAMOVE_API_SECRET=sk_test_REPLACE_LOCALLY
LALAMOVE_MARKET=SG
LALAMOVE_BASE_URL=https://rest.sandbox.lalamove.com
```

The CLI reads only those names; process environment values take precedence.
Live credentials, other hosts and markets, redirects and unsupported API paths
are refused. Requests sign exactly the JSON bytes transmitted. Errors omit raw
provider responses and credentials. Provider IDs remain strings to preserve
19-digit precision. SGD decimal prices are converted to integer minor units.

From the repository root:

```powershell
node services/fulfilment/scripts/lalamove-spike.mjs cities
node services/fulfilment/scripts/lalamove-spike.mjs listen .local/x05-callback-evidence.jsonl
# In another terminal, expose only localhost:8017 through a temporary HTTPS tunnel.
# Register that URL with the fixed /x05/lalamove path:
node services/fulfilment/scripts/lalamove-spike.mjs webhook https://YOUR-TUNNEL/x05/lalamove
node services/fulfilment/scripts/lalamove-spike.mjs quote
node services/fulfilment/scripts/lalamove-spike.mjs create QUOTATION_ID
node services/fulfilment/scripts/lalamove-spike.mjs status ORDER_ID
node services/fulfilment/scripts/lalamove-spike.mjs cancel ORDER_ID
node services/fulfilment/scripts/lalamove-spike.mjs clear-webhook
node --test services/fulfilment/scripts/lalamove-spike.test.mjs
```

Use the returned IDs, not the placeholder words. Create before the quote expires.
`create` re-fetches and validates the quote, uses its stop IDs and synthetic
contacts, creates one sandbox order, then retrieves it independently. Public
Singapore landmarks are used as synthetic stops; no patient data is sent.
`create` prints the created ID before inspection so a failed follow-up can be
retried with `status`. Do not blindly retry order creation after a network error:
the provider's Request-ID is not documented as an idempotency key. Check the
sandbox portal first. `cancel` verifies X05 metadata before cancelling.
After verified cancellation, clear the temporary webhook and stop the listener
and tunnel. Registration replaces the sandbox account's webhook URL; if one was
already configured, save it before starting and restore it with `webhook` afterward.

## Callback verification

The receiver binds only to `127.0.0.1:8017`; its sole POST path is
`/x05/lalamove`. An empty registration probe receives 200 but is not recorded as
an authenticated event. Other messages must have the configured sandbox API key,
integer timestamp within the 24-hour retry window (at most five minutes ahead),
and a constant-time matching HMAC-SHA256 signature. The signed string is:

```text
timestamp + CRLF + POST + CRLF + /x05/lalamove + CRLF + CRLF + JSON.stringify(event.data)
```

This follows the provider tutorial's linked validation example. It signs the
serialized `data` object, rather than the entire callback body. Node is used to
match JavaScript serialization, including nested Unicode and numeric values.
`eventId` and `eventType` are outside that signed data, so they are never treated
as authoritative application state. No payload field is hardcoded into the
signature input. The timestamp in actual callbacks was seconds, matching the
provider example; outgoing API timestamps use milliseconds.

Non-POST/wrong paths return 404; malformed, tampered, stale or wrong-key messages
return 400; bodies over 64 KiB return 413. Duplicate signatures are acknowledged
without duplicate evidence during this process's lifetime. The bounded in-memory
cache is spike-only: durable deduplication, queueing, ordering/reconciliation,
tenant/order matching and application updates belong to D05/D06. Retried or
out-of-order callbacks must not regress application delivery status.

Only receipt time, authentication result, order ID and status are retained in the
optional ignored evidence file. No key, signature, share link, contact, address
or raw provider response is logged. Unknown signed events can produce null
order/status, which is evidence of authentication only.

## Actual provider evidence, 18 October 2026

| Check | Result |
| --- | --- |
| Authenticated `GET /v3/cities` | HTTP 200, Singapore motorcycle service available |
| Create and retrieve quotation | `3608770529626608275`, SGD 7.80 (780 minor units), MOTORCYCLE |
| Quotation expiry | `2026-10-18T07:49:36.00Z`, validated before creation |
| Create and independently retrieve order | `3608133045767029417`, linked quotation, X05 metadata, SGD 7.80, ASSIGNING_DRIVER |
| Callback registration | HTTP success and empty-body probe acknowledged through temporary HTTPS tunnel |
| Real signed order callbacks | Signature verified, matching order ID and ASSIGNING_DRIVER at `07:41:15Z` |
| Cancellation | DELETE succeeded; independent GET returned CANCELED |
| Real signed cancellation | Matching order ID and CANCELED at `07:41:47Z` |
| Cleanup | Test order cancelled; `PATCH /v3/webhook` with empty URL successfully cleared the temporary registration; receiver/tunnel stopped |

Ten local Node checks passed, including an independent HMAC vector, actual loopback HTTP requests, altered
signatures/data, wrong key/secret/path, stale/future timestamps, duplicates, body
limits, exact outbound signing, production refusal, quote expiry/precision and
order linkage. These negative checks use synthetic events; the successful order
and cancellation callback checks above came from Lalamove itself. CI also runs
the Node tests without credentials or external requests.

Consumers must use the actual provider expiry, avoid assuming a fixed lifetime,
and handle provider expiry errors. This evidence establishes
sandbox feasibility only, not real driver pickup/completion, production access,
medication handling, application integration or AWS callback reachability.
X05 is complete after merged PR #167; all ten push/PR CI checks passed.

References: [API](https://developers.lalamove.com/) and
[webhook tutorial](https://developers.lalamove.com/files/v3_Webhook_v1.5.pdf).
