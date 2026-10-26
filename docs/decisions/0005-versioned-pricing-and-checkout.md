# ADR 0005: Versioned pricing and frozen checkout quotes

## Status

Accepted for Phase 5.

## Context

Rates change over time, but a vehicle's charge must remain reproducible. Checkout must be safe under
retries and concurrency, and older sessions must not silently inherit a rate that may not have
existed when they entered.

## Decision

### Pricing is captured at entry

Entry locks the lot before reading the active policy, preserving the shared order:

```text
lot → gate → vehicle → pricing policy → spot
```

The policy is selected from the vehicle type. A car allocated a large spot still uses car pricing.
The session and its one-to-one `PricingSnapshot` are inserted in the same transaction. Missing
pricing aborts entry with `PRICING_NOT_CONFIGURED` and leaves no session.

### Policies and snapshots are immutable versions

ADMIN publication locks the lot, retires the prior active policy, assigns the next version, and
publishes the replacement atomically. PostgreSQL permits at most one active policy per lot and
vehicle type. Financial fields are not edited; retiring a policy changes only `is_active` and never
changes existing snapshots.

Snapshots copy the policy ID/version, currency, rate, grace, cap, and calculator version. Checkout
therefore never recalculates historical charges from the current policy.

### HOURLY_V1 billing semantics

Elapsed duration is calculated between explicit timezone-aware instants after conversion to UTC.
Grace is a free threshold, not a deduction: a duration at or below grace is free, while one
microsecond beyond grace bills the entire elapsed duration. Each started hour rounds upward.

Duration is split into consecutive 24-hour blocks from entry. The daily cap applies independently
to every full block and to the final partial block. Grace is checked once against total duration and
does not restart. All arithmetic uses `Decimal`; breakdown size is constant regardless of stay
length.

### Checkout freezes the amount

Checkout uses the order `lot → session`, captures the server clock once, resolves the snapshot's
server-controlled calculator version, creates one immutable quote, and transitions `ACTIVE` to
`PAYMENT_PENDING` in one transaction. A repeated checkout in `PAYMENT_PENDING` returns the persisted
quote without observing a later clock.

The quote is the amount due for this product version; parking fees do not continue accruing after
checkout. Quote expiry or exit-delay charges require a future product decision.

Checkout does not release occupancy. `PAYMENT_PENDING` remains an open session, the spot stays
occupied, `closed_at` stays null, and neither `PAID` nor `CLOSED` is set in Phase 5. Zero-value quotes
also remain payment pending.

### Existing sessions require an explicit decision

The schema permits a legacy session to have no snapshot. Checkout then returns
`SESSION_PRICING_NOT_CONFIGURED`. The `backfill_pricing_snapshots` command requires an explicit
policy ID, verifies lot and vehicle-type compatibility, is idempotent, and never overwrites an
existing snapshot. Current prices are never automatically projected backward.

## Checkout sequence

```mermaid
sequenceDiagram
    actor Staff as ADMIN/OPERATOR
    participant API as Checkout API
    participant Service as Checkout service
    participant Calc as HOURLY_V1
    participant DB as PostgreSQL

    Staff->>API: POST /parking-sessions/{id}/checkout/ {}
    API->>API: JWT, role, strict empty body
    API->>Service: checkout(session ID, actor)
    Service->>DB: BEGIN; lock lot → session
    Service->>DB: read immutable pricing snapshot and existing quote
    alt PAYMENT_PENDING with quote
        DB-->>Service: original quote
    else ACTIVE without quote
        Service->>Service: capture server timestamp once
        Service->>Calc: snapshot + entered_at + calculated_until
        Calc-->>Service: Decimal amount + bounded breakdown
        Service->>DB: insert quote; set PAYMENT_PENDING; COMMIT
    end
    Service-->>API: persisted quote
    API-->>Staff: HTTP 200
```

## Updated relationships

```mermaid
erDiagram
    PARKING_LOT ||--o{ PRICING_POLICY : versions
    USER ||--o{ PRICING_POLICY : publishes
    PARKING_SESSION ||--o| PRICING_SNAPSHOT : captures
    PRICING_POLICY ||--o{ PRICING_SNAPSHOT : source
    PARKING_SESSION ||--o| CHECKOUT_QUOTE : freezes
    USER ||--o{ CHECKOUT_QUOTE : creates

    PRICING_POLICY {
        bigint id PK
        bigint parking_lot_id FK
        string vehicle_type
        integer version
        string currency
        decimal hourly_rate
        integer grace_minutes
        decimal daily_cap
        boolean is_active
        bigint created_by_id FK
    }
    PRICING_SNAPSHOT {
        bigint id PK
        bigint parking_session_id FK_UK
        bigint pricing_policy_id FK
        integer policy_version
        decimal hourly_rate
        string calculator_version
    }
    CHECKOUT_QUOTE {
        bigint id PK
        bigint parking_session_id FK_UK
        datetime calculated_until
        decimal amount
        string currency
        json calculation_breakdown
        bigint created_by_id FK
    }
```

## Consequences

- Financial results remain reproducible after policy replacement or retirement.
- Checkout retries and concurrent requests return one persisted quote.
- The product deliberately separates checkout, payment, and physical exit.
- Payments, webhooks, refunds, exit, Redis, Celery, taxes, discounts, and lost-ticket fees remain
  outside Phase 5.
