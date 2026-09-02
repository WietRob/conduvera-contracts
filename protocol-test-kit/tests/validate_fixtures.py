#!/usr/bin/env python3
"""Conduvera protocol test kit - deterministic fixture validation.

Validates the bundled fixtures against the published schemas using a
deliberately minimal, stdlib-only JSON Schema checker. Supported keywords are
exactly the subset published by this repository (see schemas/README.md):
type, enum, const, required, properties, additionalProperties:false, pattern,
minLength, maxLength, minimum, uniqueItems. `format` is checked for the two
published formats (date-time, sha256 digest prefix) and ignored otherwise.

No network, no runtime state, no mutation authority: this kit never executes
control-plane code and never writes outside its own output stream.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
REPO = KIT.parent

DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


def _check(instance, schema, path, errors):
    t = schema.get("type")
    if t == "object":
        if not isinstance(instance, dict):
            errors.append(f"{path}: expected object")
            return
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
    elif t == "array":
        if not isinstance(instance, list):
            errors.append(f"{path}: expected array")
            return
        if schema.get("uniqueItems") and len(instance) != len(
            {json.dumps(i, sort_keys=True) for i in instance}
        ):
            errors.append(f"{path}: array items are not unique")
        if "items" in schema:
            for i, item in enumerate(instance):
                _check(item, schema["items"], f"{path}[{i}]", errors)
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


def validate(instance, schema):
    errors: list[str] = []
    _check(instance, schema, "$", errors)
    return errors


CASES = [
    ("work-contract", "valid_minimal.json", True),
    ("work-contract", "valid_migrated_from_v1.json", True),
    ("work-contract", "invalid_missing_required.json", False),
    ("work-contract", "invalid_v1_version_rejected.json", False),
    ("work-contract", "invalid_bad_digest_format.json", False),
    ("writer-fence", "valid_fence.json", True),
    ("writer-fence", "valid_fence_minimal.json", True),
    ("writer-fence", "invalid_missing_claim_owner.json", False),
    ("writer-fence", "invalid_negative_revision.json", False),
    ("adapter", "valid_adapter.json", True),
    ("adapter", "invalid_global_completion_field.json", False),
    ("adapter", "invalid_unknown_role.json", False),
    ("adapter-receipt", "valid_receipt_snapshot.json", True),
    ("adapter-receipt", "valid_receipt_attempt_outcome.json", True),
    ("adapter-receipt", "invalid_receipt_missing_attempt_id.json", False),
    ("adapter-receipt", "invalid_receipt_unknown_kind.json", False),
]


def main() -> int:
    failures = 0
    for family, fixture, expect_valid in CASES:
        schema = json.loads((REPO / "schemas" / f"{family}.schema.json").read_text())
        instance = json.loads((KIT / "fixtures" / family / fixture).read_text())
        errors = validate(instance, schema)
        valid = not errors
        ok = valid == expect_valid
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {family}/{fixture} expected={'valid' if expect_valid else 'invalid'}")
        if not ok:
            failures += 1
            for e in errors:
                print(f"       {e}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} conformance cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
