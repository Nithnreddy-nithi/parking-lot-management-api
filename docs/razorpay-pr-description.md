# Problem

Phase 6 had only a deterministic simulator. It could not create real checkout orders, validate signed
callbacks or webhooks, reconcile Razorpay state, or record controlled refunds.

# Change

- Add the official Razorpay SDK behind the existing provider boundary.
- Create server-side Orders using stable attempt UUID receipts and expose safe Checkout metadata.
- Verify Checkout signatures, fetch captured payments, and reuse transactional settlement logic.
- Add raw-body HMAC-verified, event-ID-deduplicated payment/refund webhooks.
- Add immutable refund history, partial-refund limits, permissions, reads, and reconciliation.
- Add fail-fast production credentials, Compose settings, migration, tests, OpenAPI, and ADR docs.

# Validation

- `ruff check .`
- `ruff format --check .`
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py spectacular --file <temporary-schema> --validate`
- `pytest`
- `docker build --target runtime -t parking-lot-api:razorpay .`

# Migrations

- `parking_payments.0002_*` adds Razorpay order references, refunds, webhook delivery metadata,
  provider/event uniqueness, and refund/webhook consistency checks.
- Existing simulator attempts and settlements remain valid; no data rewrite is required.

# Risks

- Live keys and real financial operations were not used during automated verification.
- Webhook endpoints require public HTTPS and correct Test/Live Dashboard configuration.
- An ambiguous refund-create response without a stored provider refund ID needs Dashboard lookup
  before reconciliation; blindly creating a replacement can duplicate a refund.
- Manual Dashboard refunds are external writes and require operational reconciliation.
