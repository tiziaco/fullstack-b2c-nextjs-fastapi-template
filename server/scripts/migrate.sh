#!/bin/bash
#
# Release phase: bring the database schema up to date, then exit.
#
# Run by the one-shot `migrate` service in docker-compose.*.yml. `server` is
# gated on this exiting 0 (`depends_on: condition: service_completed_successfully`),
# so a non-zero exit here fails the whole `up` and the app is never started
# against a schema it doesn't expect.
#
# This deliberately does NOT run from the app's entrypoint. Coupling migrations
# to app startup turns a migration failure into a crash-loop instead of a
# legible failed deploy step, and races when more than one replica starts.
#
# Add further release-phase steps here (seeding, backfills, first-admin
# bootstrap) rather than in the compose `command:` — this script is the single
# place both compose files point at. Anything added must be IDEMPOTENT: this
# runs on every `up`, including a plain restart with nothing to change.

set -e

echo -e "\n========================================="
echo "Running database migrations..."
echo "========================================="

if python -m alembic upgrade head; then
    echo "Migrations completed successfully"
else
    echo "ERROR: Database migrations failed"
    exit 1
fi
