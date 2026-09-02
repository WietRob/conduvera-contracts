# Protocol test kit

Deterministic fixtures, validator, and conformance cases for published
protocols. The kit observes supplied inputs and expected outputs only. It has
no workflow-transition, mutation, credential, approval, or merge authority.

## Layout

- `tests/validate_fixtures.py` — stdlib-only validator. Implements the
  published schema keyword subset INCLUDING minimal draft-2020-12
  allOf/if/then/else (the D0 pass-1 P2 lesson: conditionals must actually be
  enforced) plus the frozen D8_GATE_PROTOCOL rule layer:
  - GateExecutionKey derivation check (canonical array serialization);
  - GatePlan determinism (P0-P5 order, unique keys, intra-plan acyclic
    dependencies, plan_digest binding);
  - receipt content_sha256 binding, PASS-needs-evidence, SKIPPED-needs-typed-
    reason, and a global-outcome scan (no object carries a GateOutcome);
  - gate identity collision rule (gate_id + semantic_version +
    authority_domain claimed by two definitions with different
    semantic_digest is rejected);
  - right-reason assertions: every negative fixture must fail with its
    declared error class, not merely "some" error.

## Fixture families

work-contract, writer-fence (C0), adapter, adapter-receipt (D0),
gate-descriptor, gate-execution-key, gate-plan, gate-evidence-reference,
gate-execution-receipt, gate-skip-reason (D8_GATE_PROTOCOL).

Positive fixtures are named `valid_*.json`, negative fixtures
`invalid_*.json`; the gate-descriptor identity-collision pair is named
`collision_def_*.json` and is rejected as a pair.

## Run

```bash
python3 protocol-test-kit/tests/validate_fixtures.py
```

Current conformance surface: 48 cases (18 positive / 30 negative), all green;
every negative fails for its declared reason.
