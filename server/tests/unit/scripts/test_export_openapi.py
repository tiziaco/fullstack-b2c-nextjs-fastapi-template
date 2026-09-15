"""Tests for scripts/export_openapi.py — the contract artifact must be deterministic."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = SERVER_DIR / "scripts"
COMMITTED_SPEC = SERVER_DIR / "openapi.json"
sys.path.insert(0, str(SCRIPTS_DIR))

from export_openapi import export_spec  # noqa: E402

pytestmark = pytest.mark.unit

# Run in a child process: `settings` and the FastAPI `app` are module-level
# singletons, already constructed by the time any test here runs, so mutating
# os.environ in-process could not change the exported spec either way.
_EXPORT_IN_CHILD = (
    "import sys; sys.path.insert(0, 'scripts');"
    "from pathlib import Path;"
    "from export_openapi import export_spec;"
    "export_spec(Path(sys.argv[1]))"
)


class TestExportSpec:
    def test_writes_parseable_json(self, tmp_path):
        target = export_spec(tmp_path / "openapi.json")
        spec = json.loads(target.read_text(encoding="utf-8"))
        assert spec["openapi"].startswith("3.")
        assert "/ready" in spec["paths"]

    def test_output_is_byte_identical_across_runs(self):
        # Dict ordering churn produces enormous meaningless diffs and defeats
        # review, so the dump sorts keys. Two runs must agree exactly.
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            first = export_spec(Path(d) / "a.json").read_bytes()
            second = export_spec(Path(d) / "b.json").read_bytes()
        assert first == second

    def test_keys_are_sorted(self, tmp_path):
        target = export_spec(tmp_path / "openapi.json")
        spec = json.loads(target.read_text(encoding="utf-8"))
        assert list(spec.keys()) == sorted(spec.keys())

    def test_ends_with_a_trailing_newline(self, tmp_path):
        target = export_spec(tmp_path / "openapi.json")
        assert target.read_text(encoding="utf-8").endswith("}\n")

    def test_deployment_specific_oauth_urls_are_blanked(self, tmp_path):
        # CLERK_AUTHORIZE_URL / CLERK_TOKEN_URL are per-tenant deployment config.
        # The served schema carries the real values for Swagger's Authorize
        # button; the committed artifact must not, or whichever machine ran the
        # export stamps its own Clerk tenant into the contract and every other
        # machine sees `make check-contract` fail. Under APP_ENV=test the
        # conftest exports placeholder URLs, so this asserts on the live branch.
        target = export_spec(tmp_path / "openapi.json")
        spec = json.loads(target.read_text(encoding="utf-8"))
        flows = spec["components"]["securitySchemes"]["OAuth2AuthorizationCodeBearer"]["flows"]
        for flow in flows.values():
            for key in ("authorizationUrl", "tokenUrl", "refreshUrl"):
                assert flow.get(key, "") == "", f"{key} leaked a deployment value"

    def test_export_matches_the_committed_artifact(self, tmp_path: Path):
        """A fresh export must byte-equal what is committed.

        The same-process determinism check cannot catch a dependence on an
        environment file, because both exports read the same one. This can:
        it fails whenever the committed artifact stops being reproducible
        from the code, which is what `make check-contract` enforces in CI.
        """
        fresh = export_spec(tmp_path / "openapi.json").read_bytes()
        assert fresh == COMMITTED_SPEC.read_bytes(), (
            f"{COMMITTED_SPEC} is stale or machine-dependent. Regenerate the "
            "contract artifacts with `make check-contract` from the repo root "
            "and commit them; if the diff is only in the `info` block, "
            "something is deriving the schema's identity from settings again."
        )

    @pytest.mark.slow
    def test_environment_variables_cannot_move_the_schema_identity(self, tmp_path: Path):
        """A polluted environment must not change one byte of the artifact.

        The `info` block used to be read from `Settings`, so any `.env` file
        or exported variable setting PROJECT_NAME produced a different title,
        a different orval header in 31 generated client files, and a failing
        `make check-contract` on every machine but the one that last
        regenerated. API_V1_STR had the same reach for a wider blast radius:
        it prefixes every versioned key in `paths`, so an env file could move
        the whole route surface of the contract. Both now live in
        app/core/metadata.py; this proves the environment cannot reach either.
        """
        target = tmp_path / "openapi.json"
        polluted = {
            **os.environ,
            "PROJECT_NAME": "Polluted Name",
            "VERSION": "9.9.9",
            "DESCRIPTION": "Polluted description",
            "API_V1_STR": "/polluted",
        }
        result = subprocess.run(
            [sys.executable, "-c", _EXPORT_IN_CHILD, str(target)],
            cwd=SERVER_DIR,
            env=polluted,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert target.read_bytes() == COMMITTED_SPEC.read_bytes(), (
            "A PROJECT_NAME / VERSION / DESCRIPTION / API_V1_STR environment "
            "variable changed the exported schema. Something is deriving the "
            "API's identity or its route prefix from settings again instead of "
            "from app/core/metadata.py."
        )
