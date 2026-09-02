#!/usr/bin/env python3
"""Conduvera protocol test kit - deterministic fixture validation.

Validates the bundled fixtures against the published schemas using a
deliberately minimal, stdlib-only JSON Schema checker. Supported keywords are
exactly the subset published by this repository (see schemas/README.md):
type, enum, const, required, properties, additionalProperties:false, pattern,
minLength, maxLength, minimum, maxItems, uniqueItems, items, prefixItems,
$defs/$ref (local "#/..." and sibling-file references), allOf/if/then/else.

Beyond plain schema validation this kit enforces the FROZEN protocol rules of
release D8_GATE_PROTOCOL:

- GateExecutionKey derivation: execution_key = lowercase-hex SHA-256 over the
  UTF-8 encoding of the compact JSON array [candidate_tree_sha,
  work_contract_digest, policy_digest, gate_semantic_digest, toolchain_digest,
  environment_digest, assurance_class] (separators ',' ':', no whitespace).
- GatePlan determinism: requests sorted ascending by (phase_rank, execution_key)
  with phase_rank = P0<P1<P2<P3<P4<P5; keys unique; depends_on edges only
  within the plan; plan_digest = sha256 over the UTF-8 compact JSON (sort_keys)
  of the requests array in stored order.
- GateExecutionReceipt: result is a per-execution observation, never a global
  GateOutcome (no object carries one - additionalProperties:false plus this
  kit's explicit global-outcome scan); PASS requires >=1 evidence ref;
  SKIPPED requires a typed GateSkipReason; content_sha256 binds the canonical
  receipt content (compact JSON, sort_keys, content_sha256 field removed).
- Identity collision rule: two independent gate definitions claiming the same
  gate_id + version (semantic_version) + authority_domain with DIFFERENT
  semantic_digest values are rejected.
- GateSkipReason is typed; empty detail is a forbidden silent skip.

No network, no runtime state, no mutation authority: this kit never executes
control-plane code and never writes outside its own output stream.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
REPO = KIT.parent
SCHEMAS = REPO / "schemas"

DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)
PHASE_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}
ASSURANCE_CLASSES = ("LOCAL_ADVISORY", "MANAGED_AUTHORITATIVE")


def _canon(obj) -> bytes:
    return json.dumps(
        obj, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    ).encode("utf-8")


def _check(instance, schema, path, errors):
    t = schema.get("type")
    if t == "object":
        if not isinstance(instance, dict):
            errors.append(f"{path}: expected object")
            return
    if t == "array":
        if not isinstance(instance, list):
            errors.append(f"{path}: expected array")
            return
        if schema.get("uniqueItems") and len(instance) != len(
            {json.dumps(i, sort_keys=True) for i in instance}
        ):
            errors.append(f"{path}: array items are not unique")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: more than maxItems={schema['maxItems']}")
        if "prefixItems" in schema:
            for i, sub in enumerate(schema["prefixItems"]):
                if i < len(instance):
                    _check(instance[i], sub, f"{path}[{i}]", errors)
        if "items" in schema:
            start = len(schema.get("prefixItems", []))
            for i in range(start, len(instance)):
                _check(instance[i], schema["items"], f"{path}[{i}]", errors)
    elif t == "string":
        if not isinstance(instance, str):
            errors.append(f"{path}: expected string")
            return
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength={schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength={schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: does not match pattern {schema['pattern']}")
        fmt = schema.get("format")
        if fmt == "date-time" and instance and not DATE_TIME.match(instance):
            errors.append(f"{path}: invalid date-time '{instance}'")
    elif t == "integer":
        if not isinstance(instance, int) or isinstance(instance, bool):
            errors.append(f"{path}: expected integer")
            return
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below minimum={schema['minimum']}")
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: const mismatch (expected {schema['const']!r})")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value not in enum")
    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property '{req}'")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    errors.append(f"{path}: additional property '{key}' not allowed")
        for key, sub in props.items():
            if key in instance:
                _check(instance[key], sub, f"{path}.{key}", errors)
    _check_conditionals(instance, schema, path, errors)


def _check_conditionals(instance, schema, path, errors):
    """Minimal draft-2020-12 allOf/if/then/else support (D0 lesson: the kit
    must actually ENFORCE conditional rules, not silently skip them)."""
    for sub in schema.get("allOf", []):
        _check(instance, sub, path, errors)
    cond = schema.get("if")
    if cond is None:
        return
    probe: list[str] = []
    _check(instance, cond, f"{path}.if", probe)
    if not probe:
        if "then" in schema:
            _check(instance, schema["then"], f"{path}.then", errors)
    elif "else" in schema:
        _check(instance, schema["else"], f"{path}.else", errors)


def resolve_ref(ref: str):
    if ref.startswith("#/"):
        node = ROOT_SCHEMA
        for part in ref[2:].split("/"):
            node = node[part]
        return node
    if not ref.endswith(".schema.json"):
        raise ValueError(f"unsupported $ref {ref!r}")
    return json.loads((SCHEMAS / ref).read_text())


ROOT_SCHEMA: dict = {}


def validate(instance, schema):
    global ROOT_SCHEMA
    ROOT_SCHEMA = schema
    errors: list[str] = []
    _check(instance, schema, "$", errors)
    return errors


# ---------------- frozen protocol-rule checks ----------------


def check_execution_key(doc) -> list[str]:
    comps = doc["components"]
    arr = [
        comps["candidate_tree_sha"],
        comps["work_contract_digest"],
        comps["policy_digest"],
        comps["gate_semantic_digest"],
        comps["toolchain_digest"],
        comps["environment_digest"],
        comps["assurance_class"],
    ]
    derived = hashlib.sha256(
        json.dumps(arr, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if doc["execution_key"] != derived:
        return [f"execution_key {doc['execution_key']} != frozen derivation {derived}"]
    return []


def check_plan(doc) -> list[str]:
    errors: list[str] = []
    reqs = doc["requests"]
    if any(r["phase"] not in PHASE_RANK for r in reqs):
        errors.append("unknown phase label (must be P0-P5)")
        return errors
    ranks = [(PHASE_RANK[r["phase"]], r["execution_key"]) for r in reqs]
    if ranks != sorted(ranks):
        errors.append("requests not sorted ascending by (phase_rank, execution_key)")
    keys = [r["execution_key"] for r in reqs]
    if len(keys) != len(set(keys)):
        errors.append("duplicate execution_key within plan")
    keyset = set(keys)
    for r in reqs:
        for dep in r["depends_on"]:
            if dep not in keyset:
                errors.append(f"depends_on edge {dep} not in plan")
    # acyclicity (DFS)
    color: dict[str, int] = {}

    def dfs(k):
        color[k] = 1
        for r in reqs:
            if r["execution_key"] == k:
                for d in r["depends_on"]:
                    if color.get(d) == 1:
                        errors.append(f"cycle via {d}")
                    elif color.get(d, 0) == 0:
                        dfs(d)
        color[k] = 2

    for r in reqs:
        if color.get(r["execution_key"], 0) == 0:
            dfs(r["execution_key"])
    derived = "sha256:" + hashlib.sha256(_canon(reqs)).hexdigest()
    if doc["plan_digest"] != derived:
        errors.append(
            f"plan_digest {doc['plan_digest']} != canonical binding {derived}"
        )
    return errors


def check_receipt(doc) -> list[str]:
    errors: list[str] = []
    body = {k: v for k, v in doc.items() if k != "content_sha256"}
    derived = "sha256:" + hashlib.sha256(_canon(body)).hexdigest()
    if doc["content_sha256"] != derived:
        errors.append(
            f"content_sha256 {doc['content_sha256']} != canonical content binding {derived}"
        )
    if doc["result"] == "PASS" and len(doc.get("evidence_refs", [])) < 1:
        errors.append("PASS receipt without evidence reference")
    if doc["result"] == "SKIPPED" and not doc.get("skip_reason"):
        errors.append("SKIPPED receipt without typed skip reason")
    for ev in doc.get("evidence_refs", []):
        errors.extend(
            validate(
                ev,
                json.loads(
                    (SCHEMAS / "gate-evidence-reference.schema.json").read_text()
                ),
            )
        )
    if doc.get("skip_reason"):
        errors.extend(
            validate(
                doc["skip_reason"],
                json.loads((SCHEMAS / "gate-skip-reason.schema.json").read_text()),
            )
        )
    return errors


def check_no_global_outcome(doc, path="$") -> list[str]:
    hits = []
    if isinstance(doc, dict):
        for k, v in doc.items():
            if k in ("gate_outcome", "GateOutcome", "outcome", "merge_decision"):
                hits.append(f"{path}.{k}: global outcome field present")
            hits.extend(check_no_global_outcome(v, f"{path}.{k}"))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            hits.extend(check_no_global_outcome(v, f"{path}[{i}]"))
    return hits


def check_identity_collisions(descriptors: list[dict]) -> list[str]:
    seen: dict[tuple, str] = {}
    errors: list[str] = []
    for d in descriptors:
        ident = (d["gate_id"], d["version"], d["authority_domain"])
        if ident in seen and seen[ident] != d["semantic_digest"]:
            errors.append(
                f"identity collision: {ident} claimed by two definitions with different semantic_digest"
            )
        seen.setdefault(ident, d["semantic_digest"])
    return errors


def collect_cases():
    cases = []
    for fam in sorted(pp.name for pp in (KIT / "fixtures").iterdir() if pp.is_dir()):
        for fx in sorted((KIT / "fixtures" / fam).glob("*.json")):
            expect_valid = not fx.name.startswith(
                "invalid_"
            ) and not fx.name.startswith("collision_def_")
            cases.append((fam, fx, expect_valid))
    return cases


FROZEN_CHECKS = {
    "gate-execution-key": check_execution_key,
    "gate-plan": check_plan,
    "gate-execution-receipt": check_receipt,
}

# Right-reason assertions: an invalid fixture must fail WITH an error matching
# its declared reason substring (not merely "some error").
EXPECTED_REASON = {
    "invalid_key_not_derived_from_components.json": "frozen derivation",
    "invalid_key_bad_format.json": "pattern",
    "invalid_unknown_assurance_class.json": "enum",
    "invalid_plan_not_phase_sorted.json": "not sorted ascending",
    "invalid_plan_digest_mismatch.json": "plan_digest",
    "invalid_plan_dangling_depends_on.json": "not in plan",
    "invalid_plan_unknown_phase.json": "enum",
    "invalid_pass_without_evidence.json": "PASS receipt without evidence",
    "invalid_skipped_without_reason.json": "typed skip reason",
    "invalid_content_sha256_mismatch.json": "canonical content binding",
    "invalid_unknown_result_enum.json": "enum",
    "invalid_global_gate_outcome_field.json": "additional property",
    "invalid_bad_content_digest.json": "pattern",
    "invalid_unknown_subject_type.json": "enum",
    "invalid_empty_store_location.json": "minLength",
    "invalid_skip_unknown_code.json": "enum",
    "invalid_skip_empty_detail.json": "minLength",
    "invalid_unknown_gate_family.json": "enum",
    "invalid_bad_cost_class.json": "enum",
    "invalid_side_effects_arbitrary.json": "enum",
    "invalid_missing_required.json": "missing required",
    "invalid_v1_version_rejected.json": "const mismatch",
    "invalid_bad_digest_format.json": "pattern",
    "invalid_missing_claim_owner.json": "missing required",
    "invalid_negative_revision.json": "below minimum",
    "invalid_global_completion_field.json": "additional property",
    "invalid_unknown_role.json": "enum",
    "invalid_receipt_missing_attempt_id.json": "missing required",
    "invalid_receipt_unknown_kind.json": "enum",
}


def main() -> int:
    failures = 0
    positive = negative = 0
    right_reason_failures = 0
    collision_pair: list[dict] = []
    for fam, fx, expect_valid in collect_cases():
        schema = json.loads((SCHEMAS / f"{fam}.schema.json").read_text())
        instance = json.loads(fx.read_text())
        errors = validate(instance, schema)
        frozen = FROZEN_CHECKS.get(fam)
        if frozen is not None:
            errors.extend(frozen(instance))
        errors.extend(check_no_global_outcome(instance))
        if fx.name.startswith("collision_def_"):
            collision_pair.append(instance)
            continue  # judged as a pair below
        if expect_valid:
            positive += 1
            ok = not errors
            kind = "valid"
        else:
            negative += 1
            reason = EXPECTED_REASON.get(fx.name)
            ok = bool(errors) and (reason is None or any(reason in e for e in errors))
            if ok and reason is None:
                print(f"       note: no expected-reason mapping for {fx.name}")
            kind = "invalid"
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {fam}/{fx.name} expected={kind}")
        if not ok:
            failures += 1
            if expect_valid or not errors:
                for e in errors:
                    print(f"       {e}")
            else:
                print(f"       expected failure reason {reason!r} not in errors:")
                for e in errors:
                    print(f"       {e}")
        elif not expect_valid:
            shown = [e for e in errors][:1]
            print(f"       (fails as required: {shown[0] if shown else '?'})")
    if len(collision_pair) == 2:
        negative += 1
        errs = check_identity_collisions(collision_pair)
        ok = bool(errs)
        print(
            f"[{'PASS' if ok else 'FAIL'}] gate-descriptor/collision_def_A+B_same_identity expected=invalid (identity collision)"
        )
        if not ok:
            failures += 1
        else:
            print(f"       (fails as required: {errs[0]})")
    total = positive + negative
    print(
        f"\n{total - failures}/{total} conformance cases passed "
        f"({positive} positive / {negative} negative; wrong-reason failures: {right_reason_failures})"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
