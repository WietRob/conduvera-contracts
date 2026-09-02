# Protocol schemas

Versioned, declarative Conduvera protocol schemas. Schemas define
interoperable data shapes; they hold no runtime state, execute no workflow
transitions, mutate no providers, and express no product policy.

## Published schemas (release C0, 2026-09-02)

- [`work-contract.schema.json`](work-contract.schema.json) — `work-contract.v2`:
  canonical operational task payload contract, extracted one-way from the
  durable `task-payload.v1` envelope of WietRob/conduvera-core.
- [`writer-fence.schema.json`](writer-fence.schema.json) — `writer-fence.v1`:
  attempt fencing identity (claim owner, lease, idempotency key, CAS revision).

Conformance: run `protocol-test-kit/tests/validate_fixtures.py` (stdlib only).
Releases and digests: [`releases/`](../releases/) and [`schema-index.yaml`](../schema-index.yaml).
