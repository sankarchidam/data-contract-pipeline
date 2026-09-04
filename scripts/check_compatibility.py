#!/usr/bin/env python3
"""
The data-contract CI gate.

Tests a candidate schema against the *currently registered* version of a subject's
compatibility rule, WITHOUT registering it. This is what runs in CI on every pull
request that touches schemas/**, and it's what turns "please don't break consumers"
from a code-review convention into something a merge can't get past.

Usage:
    python scripts/check_compatibility.py <subject> <path-to-candidate-schema.avsc>

Exit code 0  -> compatible, safe to merge/register.
Exit code 1  -> incompatible, or the check itself couldn't run (fail closed).
"""
import argparse
import json
import sys

import requests


def check(registry_url: str, subject: str, schema_path: str) -> bool:
    with open(schema_path) as f:
        schema_str = f.read()

    # Fail fast on malformed JSON rather than letting the registry's error speak for us.
    json.loads(schema_str)

    subjects = requests.get(f"{registry_url}/subjects", timeout=10).json()
    if subject not in subjects:
        print(
            f"Subject '{subject}' has no registered version yet — nothing to break. "
            f"Treating '{schema_path}' as the first contract version. OK."
        )
        return True

    resp = requests.post(
        f"{registry_url}/compatibility/subjects/{subject}/versions/latest",
        json={"schema": schema_str, "schemaType": "AVRO"},
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()
    is_compatible = bool(result.get("is_compatible", False))

    if is_compatible:
        print(f"PASS: '{schema_path}' is compatible with the registered contract for subject '{subject}'.")
    else:
        print(f"FAIL: '{schema_path}' BREAKS the data contract for subject '{subject}'.")
        print("      Consumers still running the previous schema version would break on this change.")
        messages = result.get("messages")
        if messages:
            print("      Details:", messages)

    return is_compatible


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("subject")
    parser.add_argument("schema_path")
    parser.add_argument("--registry-url", default="http://localhost:8080/apis/ccompat/v7")
    args = parser.parse_args()

    ok = check(args.registry_url, args.subject, args.schema_path)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - CLI entrypoint, fail closed with a clear message
        print(f"error: could not complete the compatibility check: {exc}", file=sys.stderr)
        sys.exit(1)
