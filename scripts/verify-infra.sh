#!/usr/bin/env bash
# Static verification of the WS1 infrastructure layout.
# No Docker daemon required except for `docker compose config` (parse-only).
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
passes=0
skips=0
pass() { echo "PASS: $1"; passes=$((passes+1)); }
fail() { echo "FAIL: $1"; fails=$((fails+1)); }
skip() { echo "SKIP: $1"; skips=$((skips+1)); }

check() { # check <description> <command...>
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then pass "$desc"; else fail "$desc"; fi
}

# --- layout ---------------------------------------------------------------
check "infra/prometheus/prometheus.yml exists"          test -f infra/prometheus/prometheus.yml
check "infra/grafana/datasources/datasource.yml exists" test -f infra/grafana/datasources/datasource.yml
check "infra/grafana/dashboards/dashboards.yml exists"  test -f infra/grafana/dashboards/dashboards.yml
check "infra/grafana/dashboards/json/ is non-empty"     bash -c 'compgen -G "infra/grafana/dashboards/json/*.json" > /dev/null'
check "docker-compose.dev.yml exists"                   test -f docker-compose.dev.yml
check "old prometheus/ dir is gone"                     bash -c '! test -d prometheus'
check "old grafana/ dir is gone"                        bash -c '! test -d grafana'
check "old docker-compose.yml is gone"                  bash -c '! test -f docker-compose.yml'

# --- identifiers ----------------------------------------------------------
check "no bare 'app' network in prod compose" \
  bash -c '! grep -qE "^\s+- app$" docker-compose.prod.yml'
check "app-network declared in dev compose"  grep -q "app-network:" docker-compose.dev.yml
check "app-network declared in prod compose" grep -q "app-network:" docker-compose.prod.yml

# Host port 5432 collides with other projects on a shared machine. The db host
# binding must stay configurable, and the server must keep reaching db on the
# CONTAINER port 5432 regardless of what the host binding is set to.
check "db host port is configurable, not hardcoded 5432" \
  bash -c 'grep -q "POSTGRES_HOST_PORT" docker-compose.dev.yml && ! grep -qE "^\s+- \"?5432:5432" docker-compose.dev.yml'
check "server pins container-side POSTGRES_PORT" \
  grep -q "POSTGRES_PORT=5432" docker-compose.dev.yml
check "web-app package name is web-app"      grep -q '"name": "web-app"' web-app/package.json
check "server package name is server"        grep -q 'name = "server"' server/pyproject.toml

# --- makefile -------------------------------------------------------------
check "Makefile defines COMPOSE_FILE"        grep -q "COMPOSE_FILE" Makefile
check "no stale personal-finance-app images" bash -c '! grep -q "personal-finance-app" Makefile'

# docker-compose.dev.yml is not a Compose *default* filename, so any invocation
# without an explicit -f silently fails when run outside the repo root. Flag any
# line invoking a compose subcommand with no standalone -f token.
check "server/ compose invocations all pass -f" python3 -c '
import re, sys, glob
pattern = re.compile(r"(\$\(DOCKER_COMPOSE\)|docker compose).*\b(up|down|logs|config|ps|build|exec|pull|restart|stop|start)\b")
flag_pattern = re.compile(r"(^|\s)-f(\s|$)")
bad = []
files = ["server/Makefile"] + sorted(glob.glob("server/scripts/*.sh"))
for path in files:
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            if pattern.search(line) and not flag_pattern.search(line):
                bad.append("%s:%d: %s" % (path, lineno, line.strip()))
if bad:
    print("\n".join(bad), file=sys.stderr)
    sys.exit(1)
'

# The check above only sees DIRECT invocations; ensure-db-user.sh builds its
# command in a bash array, which matches no literal pattern. This one is
# indirection-proof: any server/ file talking to Compose must name the file.
check "server/ compose entry points name the compose file" python3 -c '
import glob, sys
# Comments are stripped first: the filename appearing only in a comment must not
# satisfy this check, or explaining the rule would be enough to pass it.
def code(path):
    out = []
    for line in open(path):
        out.append(line.split("#", 1)[0])
    return "\n".join(out)
uses_compose = ("DOCKER_COMPOSE", "docker compose", "DC_CMD")
bad = []
for path in ["server/Makefile"] + sorted(glob.glob("server/scripts/*.sh")):
    text = code(path)
    if any(tok in text for tok in uses_compose) and "docker-compose.dev.yml" not in text:
        bad.append(path)
if bad:
    print("compose used without naming the compose file: " + ", ".join(bad), file=sys.stderr)
    sys.exit(1)
'

# --- compose validity (parse-only; needs docker CLI, not a running daemon) --
if command -v docker >/dev/null 2>&1; then
  # Parse-only: the key's VALUE is irrelevant here, but docker-compose.dev.yml uses
  # compose's required-variable form (${VAR:?...}) so the file cannot be parsed with it
  # unset. `make` supplies it via -include web-app/apps/*/.env.local; this script is run
  # directly, and must also work on a fresh clone that has no .env.local at all.
  NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="${NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY:-pk_test_parse_check}" \
  check "docker-compose.dev.yml parses"  docker compose -f docker-compose.dev.yml config
else
  skip "docker CLI not found — dev compose parse check skipped"
fi

# Prod compose cannot be validated with `docker compose config`: it points env_file at
# ./web-app/apps/web/.env.local, which is gitignored and does not exist on a fresh
# clone. Structural validation instead: every service network reference must resolve.
if python3 -c "import yaml" >/dev/null 2>&1; then
  check "prod compose network refs all resolve" python3 -c "
import sys, yaml
d = yaml.safe_load(open('docker-compose.prod.yml'))
declared = set((d.get('networks') or {}).keys())
for name, svc in (d.get('services') or {}).items():
    for n in (svc.get('networks') or []):
        if n not in declared:
            print('unresolved network %r on service %r' % (n, name)); sys.exit(1)
sys.exit(0)
"
else
  skip "PyYAML not available — prod compose structural check skipped"
fi

echo
# Print every count, so a result never has to be reported by hand-counting.
echo "SUMMARY: $passes passed, $fails failed, $skips skipped ($((passes+fails+skips)) checks)"
if [ "$fails" -eq 0 ]; then
  echo "All infra checks passed."
else
  echo "$fails check(s) failed."
fi
exit $((fails > 0))
