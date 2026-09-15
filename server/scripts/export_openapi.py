#!/usr/bin/env python3
"""Export the FastAPI OpenAPI spec to server/openapi.json.

FastAPI builds the spec from registered routes and Pydantic models via
`app.openapi()`, so no running server, network, or database is required — only
an environment that lets `from app.main import app` import cleanly. That is what
lets the drift check run in CI with no secrets configured.

The dump sorts keys and indents by two, because the output is committed and
reviewed: without sorting, dict ordering churn produces enormous meaningless
diffs.

The artifact must be reproducible from the code alone on any machine, or
`make check-contract` reports drift for everyone but whoever last regenerated
it. The schema's `info` block is therefore code-owned (app/core/metadata.py),
and the one remaining deployment-specific value is blanked here — see
`_strip_deployment_specific_values`.
"""

import copy
import json
import sys
from pathlib import Path

from app.main import app

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "openapi.json"

# OAuth2 flow endpoints are per-Clerk-tenant deployment configuration
# (CLERK_AUTHORIZE_URL / CLERK_TOKEN_URL, read by the OAuth2 scheme in
# app/api/dependencies/authentication.py). The *served* schema needs the real
# values so Swagger UI's Authorize button talks to the right Clerk instance, but
# they must never reach the *committed* artifact: whichever machine ran the
# export would stamp its own tenant into the contract, and every other machine —
# CI, Docker, a contributor with CLERK_AUTHORIZE_URL exported — would then see
# `make check-contract` fail on a value that has nothing to do with the API's
# shape. Blanking them leaves runtime behaviour untouched and makes the artifact
# a pure function of the code.
_DEPLOYMENT_SPECIFIC_FLOW_KEYS = ("authorizationUrl", "tokenUrl", "refreshUrl")


def _strip_deployment_specific_values(spec: dict) -> dict:
    """Blank per-deployment OAuth endpoints so the artifact is machine-independent."""
    security_schemes = spec.get("components", {}).get("securitySchemes", {})
    for scheme in security_schemes.values():
        for flow in scheme.get("flows", {}).values():
            for key in _DEPLOYMENT_SPECIFIC_FLOW_KEYS:
                if key in flow:
                    flow[key] = ""
    return spec


def export_spec(output_path: Path = DEFAULT_OUTPUT) -> Path:
    """Write the OpenAPI spec to `output_path` and return it."""
    # deepcopy: app.openapi() memoises and returns the live app.openapi_schema,
    # so normalising in place would mutate what the running server serves.
    spec = _strip_deployment_specific_values(copy.deepcopy(app.openapi()))
    with output_path.open("w", encoding="utf-8") as fp:
        json.dump(spec, fp, indent=2, sort_keys=True)
        fp.write("\n")
    return output_path


def main() -> int:
    """CLI entry point: export the spec to the default path and report it."""
    target = export_spec()
    print(f"Wrote OpenAPI spec to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
