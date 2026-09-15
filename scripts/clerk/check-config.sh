#!/usr/bin/env bash
# Verify the live Clerk development instance still matches the committed baseline.
#
# The instance is configuration that lives outside the repo, changeable by anyone
# with a dashboard login and with no review and no audit trail. scripts/clerk/config.json
# is the reviewable copy; this is what notices when the two have parted company.
# It matters most for the settings whose failure mode is not an error: a re-enabled
# HIBP check refuses seeded passwords at sign-in, and a missing `role` claim looks
# like a permissions bug rather than a configuration one.
#
# Refresh-then-diff, exactly like scripts/check-contract.sh — pull-config.sh holds
# the refresh so the two commands cannot drift apart, and git is the differ.
#
# UNLIKE check-contract.sh, this needs the network and Clerk credentials. That is
# precisely why it is not in `make check` and not in either git hook: it cannot run
# on a fresh clone, in CI, or offline. Run it by hand when you suspect the dashboard
# has been touched.
#
# One blind spot, inherited from the API and documented at length in pull-config.sh:
# `clerk config pull` never returns the `session` block, so drift in session.claims
# — the role claim itself — cannot be detected here. Re-run apply-config.sh if you
# suspect it.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Two levels: this script lives in scripts/clerk/, not scripts/.
cd "$SCRIPT_DIR/../.."

BASELINE=scripts/clerk/config.json

"$SCRIPT_DIR/pull-config.sh"

echo "==> Checking for drift"
# --porcelain rather than `git diff`, for the same reason check-contract.sh uses
# it: it reports a newly untracked baseline as well as a modified one. Those two
# cases need different advice, though, so they are told apart below — an
# untracked baseline produces no `git diff` output at all, and reporting that as
# dashboard drift would send the reader looking for a change nobody made.
STATUS="$(git status --porcelain -- "$BASELINE")"

case "$STATUS" in
  "")
    ;;
  '??'*)
    echo
    echo "FAIL: $BASELINE is not committed yet."
    echo "This check compares the live instance against the committed copy, so"
    echo "there is nothing to compare against. Commit the baseline first:"
    echo "  git add $BASELINE && git commit -m 'Add Clerk instance baseline'"
    exit 1
    ;;
  *)
    echo
    echo "FAIL: the live Clerk instance no longer matches the committed baseline."
    echo "Someone changed it in the dashboard. Pick one:"
    echo
    echo "  Keep the committed values — restore the file first, because the pull"
    echo "  above already overwrote it with the instance's values:"
    echo "    git checkout -- $BASELINE && make clerk-apply-config"
    echo
    echo "  Keep the dashboard change — commit the diff below as the new baseline."
    echo
    # Against HEAD rather than the index, so a baseline that was staged but not
    # committed still shows its change instead of an empty diff.
    git --no-pager diff HEAD -- "$BASELINE"
    exit 1
    ;;
esac

echo "PASS: the development instance matches $BASELINE."
