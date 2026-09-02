# Protocol schemas

Versioned, declarative Conduvera protocol schemas. Schemas define
interoperable data shapes; they hold no runtime state, execute no workflow
transitions, mutate no providers, and express no product policy.

## Published schemas (release D8_GATE_PROTOCOL, 2026-09-02)

Public, non-authoritative gate planning and evidence protocol. No object in
this protocol carries a global gate outcome: authority over merge decisions
remains in conduvera-core.

- [`gate-descriptor.schema.json`](gate-descriptor.schema.json) —
  `gate-descriptor.v1`: one gate's planning/evidence declaration (identity,
  cost, relevance, assurance class, cache, timeout, resources, side effects,
  V2.1 gate family, authority domain, source/architecture bindings,
  non-regression basis, semantic review trigger). Identity rule:
  `gate_id` + `version` + `authority_domain` is unique; the protocol rejects
  two independent definitions claiming the same triple with different
  `semantic_digest`.
- [`gate-plan.schema.json`](gate-plan.schema.json) — `gate-plan.v1`:
  deterministic execution plan; requests sorted by the fixed P0-P5 phase
  order and execution key; unique keys; intra-plan acyclic dependencies;
  content-bound `plan_digest`.
- [`gate-execution-key.schema.json`](gate-execution-key.schema.json) —
  `gate-execution-key.v1`: SHA-256 over the canonically serialized component
  array `[candidate_tree_sha, work_contract_digest, policy_digest,
  gate_semantic_digest, toolchain_digest, environment_digest,
  assurance_class]` (exact serialization frozen in the schema description).
  assurance_class is a key component: two classes never share a key.
- [`gate-execution-receipt.schema.json`](gate-execution-receipt.schema.json) —
  `gate-execution-receipt.v1`: per-execution observation (PASS|FAIL|ERROR|
  SKIPPED|UNAVAILABLE) under exactly one assurance class; never a global
  GateOutcome; PASS requires content-bound evidence; SKIPPED requires a typed
  reason; `content_sha256` binds the receipt content.
- [`gate-evidence-reference.schema.json`](gate-evidence-reference.schema.json) —
  `gate-evidence-reference.v1`: typed, `content_sha256`-bound pointer to one
  immutable evidence artifact with subject binding and canonical store
  location.
- [`gate-skip-reason.schema.json`](gate-skip-reason.schema.json) —
  `gate-skip-reason.v1`: typed skip codes; skipping is never silent.

Conformance: run `protocol-test-kit/tests/validate_fixtures.py` (stdlib only;
enforces the frozen derivation/determinism/binding rules on top of the
published keyword subset).
Releases and digests: [`releases/`](../releases/) and [`schema-index.yaml`](../schema-index.yaml).

## Earlier releases

- C0: `work-contract.v2`, `writer-fence.v1`.
- D0: `adapter.v1`, `adapter-receipt.v1`.
