"""The OpenAPI schema satisfies the API contract convention.

The convention is documented in server/CLAUDE.md. It exists because the schema
is a published artifact: server/openapi.json is committed and generates the
frontend's hooks, types and validators. A route that violates any rule below
produces a broken or misleading client symbol, silently.
"""

import re

import pytest

from app.main import app

pytestmark = pytest.mark.unit

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}

# Explicit ids are camelCase: getMe, listConversations. FastAPI's auto-generated
# ids are snake_case and carry the path and method: health_check_health_get.
CAMEL_CASE = re.compile(r"^[a-z][A-Za-z0-9]*$")

# Streaming routes return a StreamingResponse and have no JSON body to declare.
# They are excluded from codegen by this tag; WS7 owns the hand-written client.
STREAMING_TAG = "streaming"


def _operations():
    """Yield (path, method, operation) for every operation in the schema."""
    schema = app.openapi()
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if method.lower() in HTTP_METHODS:
                yield path, method.lower(), operation


def _label(path: str, method: str) -> str:
    return f"{method.upper()} {path}"


def _success_schema(response: dict) -> dict:
    """The JSON schema a 2xx response declares, or {} when it declares none."""
    return response.get("content", {}).get("application/json", {}).get("schema", {})


class TestOperationIds:
    def test_every_operation_declares_an_explicit_camel_case_id(self):
        offenders = [
            f"{_label(p, m)} -> {op.get('operationId')!r}"
            for p, m, op in _operations()
            if not CAMEL_CASE.match(op.get("operationId", ""))
        ]
        assert not offenders, (
            "These routes rely on FastAPI's auto-generated operation_id. It becomes "
            "the frontend hook name, so declare an explicit camelCase operation_id: " + "; ".join(offenders)
        )

    def test_operation_ids_are_unique(self):
        seen: dict[str, str] = {}
        duplicates = []
        for path, method, operation in _operations():
            op_id = operation.get("operationId", "")
            if op_id in seen:
                duplicates.append(f"{op_id!r}: {seen[op_id]} and {_label(path, method)}")
            seen[op_id] = _label(path, method)
        assert not duplicates, "Duplicate operation ids collide into one generated symbol: " + "; ".join(duplicates)


class TestTags:
    def test_every_operation_declares_a_tag(self):
        offenders = [_label(p, m) for p, m, op in _operations() if not op.get("tags")]
        assert not offenders, (
            "Tags become the generated client's directory names and module "
            "boundaries. Untagged routes collapse into a 'default' bucket: " + ", ".join(offenders)
        )


class TestResponses:
    def test_every_operation_declares_a_response_body_or_204(self):
        offenders = []
        for path, method, operation in _operations():
            if STREAMING_TAG in operation.get("tags", []):
                continue
            responses = operation.get("responses", {})
            if "204" in responses:
                continue
            success_codes = [c for c in responses if c.startswith("2")]
            if not any(_success_schema(responses[c]) for c in success_codes):
                offenders.append(_label(path, method))
        assert not offenders, (
            "A route with no declared response body generates `unknown` on the "
            "client. Declare a response_model, or status_code=204 if it returns "
            "no body: " + ", ".join(offenders)
        )

    def test_no_response_schema_is_an_untyped_object(self):
        offenders = []
        for path, method, operation in _operations():
            if STREAMING_TAG in operation.get("tags", []):
                continue
            for code, response in operation.get("responses", {}).items():
                if not code.startswith("2"):
                    continue
                schema = _success_schema(response)
                if schema.get("additionalProperties") is True:
                    offenders.append(f"{_label(path, method)} ({code})")
        assert not offenders, (
            "`Dict[str, Any]` emits additionalProperties: true, which generates "
            "{[key: string]: unknown} and erases type safety. Declare a Pydantic "
            "response model: " + ", ".join(offenders)
        )
