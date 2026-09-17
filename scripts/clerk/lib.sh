#!/usr/bin/env bash
# Shared helpers for the scripts/clerk/* bootstrap scripts.
#
# Sourced, never executed. Every function here writes to one of the three env
# files, which is the one job more than one of those scripts has: bootstrap-env.sh
# writes the application keys, bootstrap-oauth.sh writes the OAuth trio, and both
# must leave the rest of the file — comments, ordering, unrelated keys — alone.
#
# Sourcing rather than copying matters more than it looks. The awk in upsert()
# encodes two portability decisions (BSD vs GNU `sed -i`, and a file with no
# trailing newline) that a second copy would silently lose the next time one of
# them was edited and the other was not.
#
#     source "$(dirname "$0")/lib.sh"

# Seed a missing env file from its example, the way server/scripts/set_env.sh does,
# so a fresh clone works rather than failing partway through.
ensure_env_file() { # ensure_env_file <path> <example path>
  if [ ! -f "$1" ]; then
    if [ ! -f "$2" ]; then
      echo "FAIL: neither $1 nor $2 exists."
      exit 1
    fi
    cp "$2" "$1"
    echo "    created $1 from $(basename "$2")"
  fi
}

# Replace a key in place, or append it, leaving comments, blank lines and every
# other key untouched. awk to a sibling temp rather than `sed -i`, whose syntax
# differs between BSD (macOS) and GNU.
upsert() { # upsert <file> <key> <value> [quoted]
  local file=$1 key=$2 value=$3 quoted=${4:-} line
  if [ -n "$quoted" ]; then line="$key=\"$value\""; else line="$key=$value"; fi
  if grep -qE "^[[:space:]]*(export[[:space:]]+)?${key}=" "$file" 2>/dev/null; then
    awk -v key="$key" -v line="$line" '
      $0 ~ "^[[:space:]]*(export[[:space:]]+)?" key "=" { print line; next }
      { print }
    ' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
  else
    # A file not ending in a newline would otherwise glue the new key onto the
    # last one.
    [ -s "$file" ] && [ -n "$(tail -c 1 "$file")" ] && printf '\n' >> "$file"
    printf '%s\n' "$line" >> "$file"
  fi
}

# Refuse to run against anything but a development instance. Guards the TARGET,
# not the credential — see the long note in seed-users.sh for why checking
# $CLERK_SECRET_KEY is the wrong test.
require_dev_instance() { # require_dev_instance <app id>
  if ! clerk apps list --json | jq -e --arg app "$1" '
    .[] | select(.application_id == $app) | .instances[]
    | select(.environment_type == "development") | .publishable_key
    | startswith("pk_test_")
  ' > /dev/null 2>&1; then
    echo "FAIL: $1 has no development instance issuing pk_test_ keys."
    echo "Check CLERK_APP_ID in the root .env against 'clerk apps list'."
    exit 1
  fi
}
