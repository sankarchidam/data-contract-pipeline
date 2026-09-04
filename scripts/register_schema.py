#!/usr/bin/env python3
"""
Register a schema version for a subject, and optionally lock in a compatibility rule.

Used two ways in this repo:
  1. The `registry-setup` one-shot container uses it to bootstrap the live pipeline:
     register the v1 contract and set the subject's compatibility mode to BACKWARD.
  2. The CI workflow uses it to seed a throwaway registry with whatever schema is
     currently on `main`, before testing a pull request's proposed schema against it
     (see scripts/check_compatibility.py).
"""
import argparse
import sys
import time

import requests


def wait_for_registry(registry_url: str, timeout: int = 90) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            resp = requests.get(f"{registry_url}/subjects", timeout=5)
            if resp.status_code == 200:
                return
        except requests.exceptions.RequestException as exc:
            last_error = exc
        time.sleep(2)
    raise RuntimeError(f"Schema registry at {registry_url} did not become ready in time: {last_error}")


def register(registry_url: str, subject: str, schema_path: str, compatibility: str | None) -> None:
    with open(schema_path) as f:
        schema_str = f.read()

    resp = requests.post(
        f"{registry_url}/subjects/{subject}/versions",
        json={"schema": schema_str, "schemaType": "AVRO"},
        timeout=10,
    )
    resp.raise_for_status()
    print(f"Registered '{schema_path}' for subject '{subject}': {resp.json()}")

    if compatibility:
        resp = requests.put(
            f"{registry_url}/config/{subject}",
            json={"compatibility": compatibility},
            timeout=10,
        )
        resp.raise_for_status()
        print(f"Set compatibility rule for '{subject}' to {compatibility}: {resp.json()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("subject", help="Registry subject, e.g. orders.order-created-value")
    parser.add_argument("schema_path", help="Path to the .avsc file to register")
    parser.add_argument("--registry-url", default="http://localhost:8080/apis/ccompat/v7")
    parser.add_argument(
        "--set-compatibility",
        choices=["BACKWARD", "BACKWARD_TRANSITIVE", "FORWARD", "FORWARD_TRANSITIVE", "FULL", "FULL_TRANSITIVE", "NONE"],
        default=None,
        help="If set, also configure the subject's compatibility rule.",
    )
    parser.add_argument("--wait", action="store_true", help="Wait for the registry to be reachable first.")
    args = parser.parse_args()

    if args.wait:
        wait_for_registry(args.registry_url)

    register(args.registry_url, args.subject, args.schema_path, args.set_compatibility)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - CLI entrypoint, surface any failure plainly
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
