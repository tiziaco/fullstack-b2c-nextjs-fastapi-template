# Clerk Webhooks — Setup Procedure

How to wire a Clerk instance to this app's webhook endpoint. Repeat once per
Clerk instance (development and production are separate instances with
separate endpoints and **separate signing secrets**).

---

## What you are creating

| Thing | Where it lives | Scope |
|---|---|---|
| ngrok static domain | ngrok dashboard | One per ngrok account, permanent |
| Webhook endpoint | Clerk dashboard | One per Clerk instance |
| Signing secret (`whsec_…`) | Generated *with* the endpoint | One per endpoint |

**There is no global signing secret.** It does not exist until the endpoint
exists, and it is not on the API Keys page. If you are looking for it before
creating an endpoint, you will not find it.

---

## 1. ngrok (development only, one time)

Production is publicly reachable and needs none of this.

1. Create an ngrok account (free tier is sufficient — 1 GB/month and 3
   concurrent endpoints, far above webhook testing needs).
2. Dashboard → **Domains**. Every account including free gets one permanent
   static domain, e.g. `dapper-cat-1234.ngrok-free.app`. Claim it.
3. Dashboard → **Your Authtoken**. Copy it. It is ~49 characters with **no
   prefix**. The dashboard shows several other values that look like secrets but
   are resource IDs and will not authenticate: `rd_…` (reserved domain, on the
   Domains tab), `cr_…` (credential), `ak_…` (API key). Make sure the workspace
   picker is on the workspace that owns the domain from step 2 — authtokens and
   domains are both scoped to it.
4. Add both to the **root** `.env` (beside `GRAFANA_ADMIN_PASSWORD`):

   ```env
   NGROK_AUTHTOKEN=2abc...
   NGROK_DOMAIN=dapper-cat-1234.ngrok-free.app
   ```

The static domain is the entire point: the URL registered in Clerk survives
container and host restarts, so this step is never repeated.

If you also have ngrok installed on the host (`brew install ngrok`), its config
file — `~/Library/Application Support/ngrok/ngrok.yml` — **takes precedence over
the `NGROK_AUTHTOKEN` environment variable**. A stale token there authenticates
as a different account and rejects the domain with `ERR_NGROK_320`, whatever
`.env` says. Both paths already avoid this: `make dev-tunnel` passes
`--authtoken` explicitly, and the compose `ngrok` service has no config file.
This is the canonical note — `CLAUDE.md` and `README.md` link here.

---

## 2. Create the endpoint in Clerk

1. Clerk Dashboard → **check the instance switcher first**. Development and
   production are different instances. Configuring the wrong one is the most
   common mistake here and produces a silent "no events ever arrive".
2. Navigate to **Webhooks** → **Add Endpoint**.
3. **Endpoint URL:**

   | Instance | URL |
   |---|---|
   | Development | `https://<NGROK_DOMAIN>/api/v1/webhooks/clerk` |
   | Production | `https://<your-api-domain>/api/v1/webhooks/clerk` |

4. **Message Filtering** — subscribe to exactly these three events:

   - `user.created`
   - `user.updated`
   - `user.deleted`

   Select them from the catalog rather than typing them.

   Subscribing to more is not harmless: unhandled types are logged and
   discarded, which is noise, and `session.*` events are high volume.

5. **Create.** You are redirected to the endpoint's settings page.

The endpoint does not need to be reachable at creation time. Clerk records
failed deliveries and they can be replayed from this page later.

---

## 3. Copy the signing secret

On the endpoint's settings page, find **Signing Secret** and reveal it. It
looks like `whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw`.

| Environment | Where it goes |
|---|---|
| Development | `server/.env.development` |
| Production | Your hosting platform's env vars / secret manager — **never a file in the image** |

```env
CLERK_WEBHOOK_SIGNING_SECRET=whsec_...
```

The var must reach the process as a real environment variable.
`scripts/set_env.sh` exports it for host-side `make dev`; Docker Compose
injects it via `env_file:`. It is enforced at container start by
`REQUIRED_ENV_VARS` in `scripts/docker-entrypoint.sh` — a missing value fails
the container with a named error rather than producing mysterious 401s.

### `.env.test`

Tests need a syntactically valid secret, never the real one. svix base64-decodes
the value in its `Webhook` constructor, so `whsec_dummy` raises before any test
asserts anything. Use any valid `whsec_<base64>` string:

```env
CLERK_WEBHOOK_SIGNING_SECRET=whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw
```

---

## 4. Verify

```bash
make docker-run        # from the repo root; brings up ngrok with the stack
make docker-logs-core
```

Then in the Clerk dashboard, open the endpoint → **Testing** tab → send a
sample `user.created`. You should see:

- Clerk's delivery log for that attempt showing **204**
- A structured log line in the server naming the event type

The Testing tab is the fastest signal that verification works, and it does not
require creating or mutating a real user.

---

## 5. Production

Identical procedure against the production instance, with two differences: the
endpoint URL is the real API domain (no ngrok), and the secret goes into the
platform's secret store rather than a file.

**The dev and prod secrets are different values.** A dev secret deployed to
production rejects every real event with a 401, and because signature failures
are deliberately indistinguishable from one another, the logs will not tell you
that the *secret* is the problem. Check this first when production webhooks
fail wholesale.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Every delivery 401s | Wrong secret for this instance, or the var never reached the process. Check the container's env, not just the `.env` file. |
| No deliveries at all | Endpoint created on the wrong Clerk instance; or ngrok is down / the domain changed. |
| ngrok `ERR_NGROK_320` "domain is reserved for another account" | The authtoken in use belongs to a different account/workspace than the domain. Check the host config file, not just `.env` — it wins over the env var. Re-copy the token from **Your Authtoken** in the workspace that owns the domain. |
| ngrok `ERR_NGROK_105` "invalid authtoken" | A resource ID (`rd_`, `cr_`, `ak_`) was pasted instead of the authtoken. |
| Deliveries 404 | URL path wrong — it is `/api/v1/webhooks/clerk`. |
| Container exits at startup naming the var | `REQUIRED_ENV_VARS` doing its job. Set the secret. |
| Host-side `make dev` 401s but Docker works | The entrypoint check does not run on the host. `source scripts/set_env.sh development` first. |
| Deliveries succeed, database unchanged | Not a setup problem — check the handler logs for `webhook_event_stale` (ordering guard) or a missing-row warning. |

---

## Rotating the secret

Clerk's endpoint settings page can roll the signing secret. It takes effect
immediately, so update the environment and restart the app in the same window,
or events will 401 until you do. There is no dual-secret grace period.
