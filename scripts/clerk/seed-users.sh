#!/usr/bin/env bash
# Create the template's development users in the Clerk development instance.
#
# Signing up a dev user through the UI means receiving a verification code at a
# real mailbox and choosing a password that satisfies the instance policy — per
# user, every time you rebuild an instance. Users created through the Backend API
# skip both: their email addresses are admin-verified on creation, and
# skip_password_checks lets them carry a memorable throwaway password.
#
# scripts/clerk/dev-users.json holds the roster, and it is COMMITTED ON PURPOSE.
# The emails are fake, the passwords are throwaway, and the guard below refuses to
# run against anything but a development instance. A fork clones the repo and runs
# one command instead of reading a procedure.
#
# Two users, one per role. That is the minimum that proves anything: the platform
# has exactly two roles, and only the matched pair demonstrates the role guard
# actually guards — the admin gets 200 from GET /api/v1/admin/ping and the user
# gets 403. A single user would show neither.
#
# Idempotent. A user that already exists is left alone unless its role has drifted
# from the roster, in which case only the metadata is merged. Passwords are never
# reset, so a password you changed by hand survives a re-run.
#
# Requires 'make clerk-apply-config' to have run first. Without it, password
# sign-in may be disabled outright, and the instance's Have I Been Pwned check
# refuses these deliberately-weak passwords AT SIGN-IN even though creation
# succeeded — a failure that looks like a wrong password rather than a policy.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Two levels: this script lives in scripts/clerk/, not scripts/.
cd "$SCRIPT_DIR/../.."

ROSTER=scripts/clerk/dev-users.json

if ! command -v jq > /dev/null 2>&1; then
  echo "FAIL: jq is not installed."
  echo "Install it with 'brew install jq'."
  exit 1
fi

if [ -z "${CLERK_APP_ID:-}" ]; then
  echo "FAIL: CLERK_APP_ID is not set."
  echo "Add it to the root .env — 'make clerk-bootstrap-env' writes it there"
  echo "after creating the application. See docs/setup/clerk.md."
  exit 1
fi

if [ ! -f "$ROSTER" ]; then
  echo "FAIL: $ROSTER not found."
  echo "It is committed to the repo; restore it with 'git checkout -- $ROSTER'."
  exit 1
fi

# Guard the TARGET, not the credential. $CLERK_SECRET_KEY is the wrong thing to
# check twice over: `clerk api` ignores it entirely when --app is passed, and the
# root Makefile's `-include web-app/apps/web/.env.local` exports it into every
# make-launched process anyway. What is actually checkable is the instance we are
# about to write to — a development instance issues pk_test_ keys.
echo "==> Verifying the target is a development instance"
if ! clerk apps list --json | jq -e --arg app "$CLERK_APP_ID" '
  .[] | select(.application_id == $app) | .instances[]
  | select(.environment_type == "development") | .publishable_key
  | startswith("pk_test_")
' > /dev/null 2>&1; then
  echo "FAIL: $CLERK_APP_ID has no development instance issuing pk_test_ keys."
  echo "This script creates users with weak, committed passwords and refuses to"
  echo "run anywhere else. Check CLERK_APP_ID in the root .env against"
  echo "'clerk apps list'."
  exit 1
fi

# </dev/null matters: the roster loop below reads from a process substitution on
# stdin, and any command inside it that decided to read stdin would swallow the
# remaining entries and silently seed only the first user.
api() { clerk api "$@" --app "$CLERK_APP_ID" --instance dev --yes < /dev/null; }

created=0; updated=0; unchanged=0

while IFS= read -r entry; do
  email="$(jq -r '.email' <<< "$entry")"
  role="$(jq -r '.role' <<< "$entry")"

  # GET /users returns a bare array; tolerate a wrapped {data:[...]} shape too.
  existing="$(api "/users?email_address=$email" | jq -c 'if type == "array" then . else (.data // []) end')"
  user_id="$(jq -r '.[0].id // empty' <<< "$existing")"

  if [ -z "$user_id" ]; then
    body="$(jq -n --argjson e "$entry" '{
      email_address: [$e.email],
      password: $e.password,
      first_name: $e.first_name,
      last_name: $e.last_name,
      public_metadata: { role: $e.role },
      skip_password_checks: true,
      skip_restriction_checks: true
    }')"
    api /users -X POST -d "$body" > /dev/null
    echo "    created   $email ($role)"
    created=$(( created + 1 ))
  else
    current_role="$(jq -r '.[0].public_metadata.role // empty' <<< "$existing")"
    if [ "$current_role" = "$role" ]; then
      echo "    unchanged $email ($role)"
      unchanged=$(( unchanged + 1 ))
    else
      # /metadata does a deep merge. PATCH /users/{id} would replace
      # public_metadata wholesale and drop any other keys on the user.
      api "/users/$user_id/metadata" -X PATCH \
        -d "$(jq -n --arg r "$role" '{public_metadata: {role: $r}}')" > /dev/null
      echo "    updated   $email (${current_role:-none} -> $role)"
      updated=$(( updated + 1 ))
    fi
  fi
done < <(jq -c '.[]' "$ROSTER")

echo
echo "PASS: $created created, $updated updated, $unchanged unchanged."
echo
echo "Sign in at the web app with any of the above; the passwords are in $ROSTER."
echo "The admin should get 200 from GET /api/v1/admin/ping and the user 403."
