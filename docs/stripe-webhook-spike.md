# X04 Stripe raw-body webhook spike

Tracking: [issue #161](https://github.com/NorbertLoh/CS5224-Team-39/issues/161).

Scope: verify a sample raw-body callback using the official Stripe SDK. This
independent sample spike was requested after merging X03 tooling in PR #159.
X03's real Checkout/Connect commission verification remains blocked on clinic
onboarding in issue #158; this work does not complete that integration.

Status: implementation in progress. No application payment mutations, durable
event deduplication or outbox processing; those belong to B03/B04.
