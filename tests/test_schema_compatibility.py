"""
Local, fast-feedback version of the CI gate. Run this before you even open a PR:

    docker compose up -d schema-registry
    python scripts/register_schema.py orders.order-created-value \\
        schemas/order-created/schema.avsc --set-compatibility BACKWARD --wait
    pytest tests/

It exercises the exact same check_compatibility.check() function the CI workflow
calls, against the two example schemas in demo/, so you can see both outcomes
without touching a running pipeline.
"""
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from check_compatibility import check  # noqa: E402

REGISTRY_URL = os.environ.get("SCHEMA_REGISTRY_URL", "http://localhost:8080/apis/ccompat/v7")
SUBJECT = "orders.order-created-value"
DEMO_DIR = os.path.join(os.path.dirname(__file__), "..", "demo")


def _registry_reachable() -> bool:
    try:
        return requests.get(f"{REGISTRY_URL}/subjects", timeout=2).status_code == 200
    except requests.exceptions.RequestException:
        return False


pytestmark = pytest.mark.skipif(
    not _registry_reachable(),
    reason="schema registry not reachable at SCHEMA_REGISTRY_URL -- run `docker compose up -d schema-registry` first",
)


def test_adding_optional_field_with_default_is_compatible():
    schema_path = os.path.join(DEMO_DIR, "schema-compatible-v2.avsc")
    assert check(REGISTRY_URL, SUBJECT, schema_path) is True


def test_adding_required_field_without_default_is_rejected():
    schema_path = os.path.join(DEMO_DIR, "schema-breaking-v2.avsc")
    assert check(REGISTRY_URL, SUBJECT, schema_path) is False
