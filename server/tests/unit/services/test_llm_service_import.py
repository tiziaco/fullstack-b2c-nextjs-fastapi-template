"""Importing the application must not require LLM credentials.

`make check-contract` imports `app.main` to export the OpenAPI spec, and
`.github/workflows/api-contract.yml` runs it with no database, no `.env` and no
secrets — the spec is built from registered routes and has never needed a key.

That held only by accident until openai 2.34.0 made `OpenAI(api_key="")` raise
instead of construct. Any client built at import time turns a missing key into
an ImportError and breaks that job, which is why `LLMRegistry` in
`app/services/llm/service.py` stores configuration and builds on first use.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SERVER_DIR = Path(__file__).resolve().parents[3]


def test_app_imports_without_llm_credentials():
    """Import app.main in a child process holding an empty OPENAI_API_KEY.

    A child process is required for the same reason
    tests/unit/scripts/test_export_openapi.py uses one: `settings` and `app`
    are module-level singletons, already constructed by the time this runs, so
    mutating os.environ in-process could not change the outcome. conftest.py
    also loads .env.test into os.environ before importing the app.

    The variable is set empty rather than removed so that `load_dotenv()` in
    app/main.py cannot repopulate it from a discovered .env — python-dotenv
    does not override values already present. Empty is what CI effectively has.
    """
    env = {**os.environ, "OPENAI_API_KEY": ""}

    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
