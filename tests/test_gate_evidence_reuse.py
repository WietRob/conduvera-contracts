"""K01 contract tests: additive gate-evidence-reuse + gate-evidence-reference v2.

Validates the two NEW schema artifacts of card K01 against the reuse contract
(docs/program/transfer/REUSE_CONTRACT.md, D05):

Positive:
  - a fully-bound, admissible reuse document (status REUSED)
  - a v2 evidence reference in mode EXECUTED
  - a v2 evidence reference in mode REUSED

Negative (counterexample-first):
  - a reuse document that presents itself as an EXECUTED receipt is discarded
    (EXECUTED belongs to the frozen GateExecutionReceipt v1 document, never here)
  - an unbound target key (current_candidate_binding.tree_sha missing) is discarded
  - an unknown document type (schema const mismatch) is discarded
  - a missing admission_decision is discarded (an anonymous decision admits nothing)
  - v2 cross-mode pairings (EXECUTED pointing at a reuse doc, REUSED pointing at
    a receipt) are discarded - source binding and consumer context stay separated

Validation form (documented per the card): the `jsonschema` package is used when
importable and functional; otherwise a manual structural validator (json only)
checks exactly the keywords these contracts use: type, const, enum, pattern,
minLength, minProperties, required, properties, additionalProperties,
propertyNames, allOf, if/then and local $ref resolution. Which form actually ran
is printed by `test_reports_validation_mode` and recorded in VALIDATION_MODE.

Formats (e.g. date-time) are not enforced in either form - matching the
jsonschema default of not checking formats without an explicit FormatChecker.

The six frozen D8 v1 schemas are only READ (gate-execution-key is $ref'd by the
reuse schema); this test suite never writes them.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import pytest

SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"

REUSE_SCHEMA_PATH = SCHEMAS_DIR / "gate-evidence-reuse.schema.json"
REFERENCE_V2_SCHEMA_PATH = SCHEMAS_DIR / "gate-evidence-reference.v2.schema.json"

# All local schemas by their $id, so relative $refs resolve LOCALLY (no network).
LOCAL_REGISTRY: dict[str, dict] = {}
for _p in sorted(SCHEMAS_DIR.glob("*.schema.json")):
    _doc = json.loads(_p.read_text(encoding="utf-8"))
    if isinstance(_doc, dict) and "$id" in _doc:
        LOCAL_REGISTRY[_doc["$id"]] = _doc


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Validation engine selection (documented, deterministic)
# --------------------------------------------------------------------------
try:  # preferred form
    import jsonschema as _jsonschema
    import jsonschema.validators  # noqa: F401  (ensure submodule is loaded)
    from referencing import Registry, Resource

    _REGISTRY = Registry().with_resources(
        [(uri, Resource.from_contents(doc)) for uri, doc in LOCAL_REGISTRY.items()]
    )
    VALIDATION_MODE = "jsonschema"
except Exception:  # broken or missing -> manual structural fallback
    _jsonschema = None
    VALIDATION_MODE = "manual"


def validate(schema: dict, instance) -> None:
    """Validate `instance` against `schema`; raise AssertionError on any error."""
    if VALIDATION_MODE == "jsonschema":
        cls = _jsonschema.validators.validator_for(schema)
        cls.check_schema(schema)
        validator = cls(schema, registry=_REGISTRY)
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
        if errors:
            first = errors[0]
            location = "/".join(str(p) for p in first.path) or "<root>"
            raise AssertionError(f"{location}: {first.message}")
        return

    problems = _manual_errors(schema, instance, base_uri=schema.get("$id", ""))
    if problems:
        raise AssertionError("; ".join(problems))


# --------------------------------------------------------------------------
# Manual structural validator (fallback, json-only)
# --------------------------------------------------------------------------
def _resolve_ref(ref: str, base_uri: str) -> dict:
    target = urljoin(base_uri, ref)
    if target not in LOCAL_REGISTRY:
        raise AssertionError(f"unresolvable local $ref {ref!r} (base {base_uri!r})")
    return LOCAL_REGISTRY[target]


def _type_ok(expected: str, value) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    raise AssertionError(f"manual validator: unsupported type {expected!r}")


def _manual_errors(schema: dict, instance, base_uri: str) -> list[str]:
    errors: list[str] = []

    if "$ref" in schema:
        target = _resolve_ref(schema["$ref"], base_uri)
        return _manual_errors(target, instance, base_uri=target.get("$id", base_uri))

    if "type" in schema and not _type_ok(schema["type"], instance):
        errors.append(f"expected type {schema['type']!r}, got {type(instance).__name__}")
        return errors

    if "const" in schema and instance != schema["const"]:
        errors.append(f"expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{instance!r} not in enum {schema['enum']!r}")

    if isinstance(instance, str):
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            errors.append(f"{instance!r} does not match {schema['pattern']!r}")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"shorter than minLength {schema['minLength']}")

    if isinstance(instance, dict):
        for field in schema.get("required", []):
            if field not in instance:
                errors.append(f"missing required field {field!r}")
        properties = schema.get("properties", {})
        if "propertyNames" in schema:
            name_schema = schema["propertyNames"]
            for key in instance:
                errors.extend(_manual_errors(name_schema, key, base_uri))
        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            errors.append(f"fewer than minProperties {schema['minProperties']}")
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in properties:
                errors.extend(_manual_errors(properties[key], value, base_uri))
            elif additional is False:
                errors.append(f"unexpected field {key!r}")
            elif isinstance(additional, dict):
                errors.extend(_manual_errors(additional, value, base_uri))

    if isinstance(instance, list):
        if "items" in schema:
            for index, item in enumerate(instance):
                errors.extend(_manual_errors(schema["items"], item, base_uri))

    for sub in schema.get("allOf", []):
        errors.extend(_manual_errors(sub, instance, base_uri))

    if "if" in schema:
        if not _manual_errors(schema["if"], instance, base_uri):
            if "then" in schema:
                errors.extend(_manual_errors(schema["then"], instance, base_uri))
        elif "else" in schema:
            errors.extend(_manual_errors(schema["else"], instance, base_uri))

    return errors


# --------------------------------------------------------------------------
# Fixtures / vectors
# --------------------------------------------------------------------------
HEX40 = "1f2e3d4c5b6a798877665544332211ffeeddccb9"
HEX64 = "a" * 64
SHA = f"sha256:{HEX64}"


def _execution_key_doc() -> dict:
    return {
        "schema_version": "gate-execution-key.v1",
        "execution_key": "b" * 64,
        "components": {
            "candidate_tree_sha": HEX40,
            "work_contract_digest": SHA,
            "policy_digest": SHA,
            "gate_semantic_digest": SHA,
            "toolchain_digest": SHA,
            "environment_digest": SHA,
            "assurance_class": "MANAGED_AUTHORITATIVE",
        },
    }


def valid_reuse_doc() -> dict:
    """A fully-bound, admissible reuse document (status REUSED)."""
    return {
        "schema": "conduvera.gate-evidence-reuse.v1",
        "source_execution_key": _execution_key_doc(),
        "source_receipt_ref": {
            "store_object_id": "store://evidence-protected/grcpt_9f3ab12cde34",
            "digest_sha256": SHA,
            "rehashed": True,
        },
        "complete_relevant_input_identity": {
            "gate_id": "gate_unit_tests",
            "tools": SHA,
            "config": SHA,
            "locks": SHA,
            "environment": SHA,
            "dependencies": SHA,
            "assurance_class": "MANAGED_AUTHORITATIVE",
            "binding_mode": "INPUT_BOUND",
            "inputs": {"src/conduvera/lib.py": SHA, "tests/test_lib.py": SHA},
        },
        "current_candidate_binding": {
            "tree_sha": HEX40,
            "plan_id": "gplan_4711abcd",
        },
        "admission_decision": {
            "admitted_by": "agent:k01@conduvera",
            "admitted_at": "2026-10-07T10:15:00Z",
            "decision_digest": SHA,
        },
        "status": "REUSED",
    }


def valid_v2_reference(mode: str) -> dict:
    """A v2 evidence reference with correctly separated source binding and
    consumer context."""
    evidence_type = (
        "GATE_EXECUTION_RECEIPT_V1" if mode == "EXECUTED" else "GATE_EVIDENCE_REUSE_V1"
    )
    return {
        "schema_version": "gate-evidence-reference.v2",
        "evidence_id": "gev2_7f3e9d1a",
        "mode": mode,
        "source_binding": {
            "content_sha256": SHA,
            "store_object_id": "store://evidence-protected/obj-0042",
            "evidence_type": evidence_type,
            "produced_at": "2026-10-07T09:00:00Z",
        },
        "consumer_context": {
            "consumer_tree_sha": HEX40,
            "consumer_plan_id": "gplan_4711abcd",
        },
    }


# --------------------------------------------------------------------------
# Tests - positives
# --------------------------------------------------------------------------
def test_reports_validation_mode():
    print(f"\n[K01] validation form in effect: {VALIDATION_MODE}")
    assert VALIDATION_MODE in ("jsonschema", "manual")


def test_valid_reuse_document_is_accepted():
    schema = _load(REUSE_SCHEMA_PATH)
    validate(schema, valid_reuse_doc())


def test_valid_v2_reference_executed_is_accepted():
    schema = _load(REFERENCE_V2_SCHEMA_PATH)
    validate(schema, valid_v2_reference("EXECUTED"))


def test_valid_v2_reference_reused_is_accepted():
    schema = _load(REFERENCE_V2_SCHEMA_PATH)
    validate(schema, valid_v2_reference("REUSED"))


def test_source_execution_key_follows_frozen_v1_contract():
    """The reuse schema must $ref the FROZEN v1 execution-key schema: a key
    document violating the frozen component set must be rejected here too."""
    schema = _load(REUSE_SCHEMA_PATH)
    doc = valid_reuse_doc()
    doc["source_execution_key"]["components"]["assurance_class"] = "SUPER_AUTHORITY"
    with pytest.raises(AssertionError):
        validate(schema, doc)


# --------------------------------------------------------------------------
# Tests - negatives (card-mandated)
# --------------------------------------------------------------------------
def test_reuse_doc_presenting_as_executed_receipt_is_discarded():
    """EXECUTED is the state of the v1 receipt document, never of the reuse
    document. A reuse doc claiming EXECUTED is discarded."""
    schema = _load(REUSE_SCHEMA_PATH)
    doc = valid_reuse_doc()
    doc["status"] = "EXECUTED"
    with pytest.raises(AssertionError):
        validate(schema, doc)


def test_unbound_target_key_is_discarded():
    """current_candidate_binding.tree_sha missing -> the reuse is bound to no
    current candidate and must be discarded."""
    schema = _load(REUSE_SCHEMA_PATH)
    doc = valid_reuse_doc()
    del doc["current_candidate_binding"]["tree_sha"]
    with pytest.raises(AssertionError):
        validate(schema, doc)


def test_unknown_document_type_is_discarded():
    schema = _load(REUSE_SCHEMA_PATH)
    doc = valid_reuse_doc()
    doc["schema"] = "conduvera.gate-evidence-reuse.v2"  # unknown/newer version
    with pytest.raises(AssertionError):
        validate(schema, doc)


def test_missing_admission_decision_is_discarded():
    schema = _load(REUSE_SCHEMA_PATH)
    doc = valid_reuse_doc()
    del doc["admission_decision"]
    with pytest.raises(AssertionError):
        validate(schema, doc)


# --------------------------------------------------------------------------
# Tests - negatives (v2 mode separation)
# --------------------------------------------------------------------------
def test_v2_executed_pointing_at_reuse_doc_is_discarded():
    schema = _load(REFERENCE_V2_SCHEMA_PATH)
    ref = valid_v2_reference("EXECUTED")
    ref["source_binding"]["evidence_type"] = "GATE_EVIDENCE_REUSE_V1"
    with pytest.raises(AssertionError):
        validate(schema, ref)


def test_v2_reused_pointing_at_receipt_is_discarded():
    schema = _load(REFERENCE_V2_SCHEMA_PATH)
    ref = valid_v2_reference("REUSED")
    ref["source_binding"]["evidence_type"] = "GATE_EXECUTION_RECEIPT_V1"
    with pytest.raises(AssertionError):
        validate(schema, ref)


def test_v2_missing_consumer_context_is_discarded():
    schema = _load(REFERENCE_V2_SCHEMA_PATH)
    ref = valid_v2_reference("REUSED")
    del ref["consumer_context"]
    with pytest.raises(AssertionError):
        validate(schema, ref)
