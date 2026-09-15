"""Application identity and public API shape.

The name, version and description of this service are product identity, and the
versioned path prefix is the shape of its published interface. They are
parameterised — a fork changes them without touching Python — but the parameters
live in `server/pyproject.toml`, under `[tool.app.metadata]` and `[project]`,
rather than in `server/.env.<env>`.

That distinction is the whole point. All four values reach the committed
artifact `server/openapi.json` -- the first three verbatim in its `info` block,
`API_V1_STR` as the prefix on every versioned key in `paths` -- and orval stamps
the title into the header of every generated client file. Read from a gitignored
env file they would differ per machine, so `make check-contract` would report
drift on CI and on every fresh clone the moment anyone actually set one: the
parameter could never be used for the thing it exists for. `pyproject.toml` is
committed, so every machine and CI read the same bytes.

Changing a value there is a deliberate contract change: run `make gen-contract`
and commit the regenerated artifacts in the same commit.
"""

import tomllib
from pathlib import Path

# app/core/metadata.py -> server/. The runtime image copies pyproject.toml to the
# same place relative to app/ (see the Dockerfile's runtime stage), so this
# resolves inside the container as well as on a host checkout.
_PYPROJECT_PATH = Path(__file__).resolve().parents[2] / "pyproject.toml"

# Both failures below are fatal on purpose — a service that cannot name itself
# or its API prefix must not boot. They are re-raised with context because they
# surface at import time, where the bare exception is a traceback into a module
# called `metadata` that says nothing about pyproject.toml being read at runtime.
try:
    with _PYPROJECT_PATH.open("rb") as _fp:
        _pyproject = tomllib.load(_fp)
except FileNotFoundError as exc:
    raise RuntimeError(
        f"{_PYPROJECT_PATH} not found. It is a runtime input, not just packaging "
        "metadata: this module reads the service title, version and API prefix "
        "from it at import. An image must COPY it into the runtime stage."
    ) from exc

try:
    _metadata = _pyproject["tool"]["app"]["metadata"]

    PROJECT_NAME: str = _metadata["title"]
    VERSION: str = _pyproject["project"]["version"]
    DESCRIPTION: str = _metadata["description"]
    API_V1_STR: str = _metadata["api_v1_str"]
except KeyError as exc:
    raise RuntimeError(
        f"{_PYPROJECT_PATH} is missing the key {exc}. [tool.app.metadata] must "
        "define title, description and api_v1_str; [project] must define version."
    ) from exc
