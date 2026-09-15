# GDPR Erasure — Findings

**Status:** findings only. No decisions taken, nothing implemented from this doc.
**Originally written:** 2026-08-25, against an earlier revision of this template that
carried a second, since-removed domain model and a second, since-removed multi-role
account type alongside the plain `User`.
**Re-verified:** 2026-09-15, against the current codebase, after that hard fork removed
Clerk Organizations, the second domain model, and the in-memory role/link caches.

Related: [`gdpr-compliance-guide.md`](./gdpr-compliance-guide.md) (the general pattern
guide), [`authentication.md`](./authentication.md).

## What changed in the re-verification

Every finding below was originally split into "live today" and "for a future fork"
groups, because at the time of writing the fork was speculative. It has now happened, so
that split is gone — these are simply the current findings, renumbered. Two things the
fork removed made two 2026-08-25 findings moot entirely and are noted where they
applied:

- No more second domain model with its own retention-worthy records — the retention
  justification that used to exist for those compliance records (Art 17(3)(b)/(e)) has
  no equivalent today, and no longer needs weighing against anything.
- No more asymmetric account types with different processing bases. The platform now
  has one `User` model and a `role` attribute (`user` | `admin`); an admin is not a
  structurally different data subject, just a user with an elevated permission. The
  finding that used to occupy this space (should self-deletion work the same for both
  account types?) no longer applies as originally framed.

A third 2026-08-25 finding — that `gdpr-compliance-guide.md` was titled and framed for
"B2C Applications" — is also dropped, but for a different reason than the two above: it
isn't moot, it's **resolved**. The guide's B2C framing now matches the product it
documents.

Every other finding was re-verified against the current line numbers and still stands.

---

## The central correction

> **Article 17 does not require anonymisation. It requires erasure of personal
> data.**

Anonymisation is one route to compliance — if nothing personal remains, there is
nothing left to erase. *Actually deleting the data* is the other route, and it is
simpler. The current implementation picked neither cleanly: it does a partial
overwrite and calls the result anonymisation.

So the design question is **not** "how do we anonymise harder?" It is:

> Is there anything on the retained row we have an Art 17(3) legal basis to keep?

Today the answer is no. "Referential integrity" and "analytics" are engineering
conveniences, not legal bases.

### Two corollaries that are easy to get wrong

**Soft delete is not banned.** GDPR regulates outcomes, not techniques — it has
nothing to say about `deleted_at` columns. The real rule is that *soft delete
alone does not discharge an erasure request*, because storage is processing
(Art 4(2)) and the data is still there. Soft delete remains legitimate as a
staging step before hard deletion, under an Art 17(3) exemption, for suppression
lists — and Art 18 (restriction of processing) effectively *requires* it: when a
subject contests accuracy or objects, you must keep the data and stop using it.
Hard-deleting there would be the violation.

This means `SoftDeleteMixin`'s docstring (`app/models/base.py:36`) is a useful
developer heuristic but overstated as a legal claim. `Conversation` using it is
fine — the message content is hard-deleted from LangGraph and `name` is cleared,
so the retained row is metadata. Finding 1 below objects to the retained *link to a
person*, not the soft delete.

**There is no 30-day rule.** No number appears in the regulation. Art 17(1) says
erasure "without undue delay"; Art 12(3) separately gives one month to *respond
to the request*, which is a response deadline, not permission to hold the data
for a month. A grace window before hard deletion is an optional design choice
that needs disclosing — deleting immediately is fully compliant and simpler.
During any such window the account is deactivated: processing stops at day zero,
only storage continues.

Data under an Art 17(3) exemption is the exception, and carries its own
retention period set by whatever law created the exemption — unrelated to any
grace window.

---

## Findings

### 1. The end state is pseudonymisation, not anonymisation

`app/models/user.py:53-66` (`anonymize_user()`) overwrites the PII fields but
leaves the record identifiable by reference.

What survives erasure:

| Table | Retained |
|---|---|
| `user` | `id` (UUID, **unchanged**), `clerk_id`/`email` rewritten *from* that id, `email_verified`, `created_at`, `updated_at`, `last_synced_at`, `anonymized_at` |
| `conversation` | one row per thread — `id`, `user_id` → the user row, `created_at`, `updated_at`, `deleted_at` (`name` cleared) |

Against the three cumulative tests (Art 29 WP Opinion 05/2014, carried into EDPB
Guidelines 04/2025):

- **Singling out — fails.** `user.id` remains a stable unique key for exactly one
  person. That is the definition of a pseudonym. Recital 26 states pseudonymised
  data *remains* personal data.
- **Linkability — fails.** Every conversation row still points at that key, so a
  signup date plus a timestamped activity series stays attached to one individual.
- **Inference — partially fails.** Tenure, volume and activity timing remain readable.

The content of the PII is genuinely gone and unrecoverable from the row — that
part works. The record is simply still personal data.

**Note:** the EDPB's 2025 Coordinated Enforcement Action on the right to erasure
specifically targeted controllers presenting this state as anonymisation.

### 2. Langfuse retains message content keyed by the surviving id — *highest impact*

`app/agents/shared/observability/langfuse.py:33` sets `langfuse_user_id: user_id`
on every LLM call. No masking is configured anywhere in `app/`, so Langfuse
receives full prompts and completions.

`erase_user` never touches Langfuse.

The consequence compounds finding 1: the retained `user.id` is not a dormant pseudonym,
it is a **live join key into a third-party store that still holds the person's
conversations verbatim**. This defeats any anonymisation claim on its own,
regardless of what the `user` row looks like.

Note the asymmetry: the cascade hard-deletes LangGraph checkpoints
(`app/services/user/service.py:106`) — the correct instinct — while the same
message content sits in Langfuse untouched, on both the self-service and the
`user.deleted`-webhook erasure paths.

Needs: a Langfuse deletion path (API or documented retention), or masking at
`create_graph_config`, or both.

### 3. Partial-failure ordering leaves accounts in a split state — on one of two paths

`app/api/v1/auth.py:74` deletes from Clerk **first**, before any local work, in
`DELETE /api/v1/auth/me`. If `erase_user` then fails partway, the Clerk account is
already gone, the DB transaction rolls back, and the caller gets a 500 — identity
deleted upstream, local record intact, and the user can no longer authenticate to
retry the endpoint themselves.

The `user.deleted` webhook path does not have this problem: it never calls Clerk (a
Clerk-side deletion is what produced the event), and a raised exception returns a
non-2xx response, so svix redelivers with backoff. An admin-initiated deletion is
therefore already retryable; self-service deletion is not.

Needs: either an idempotent/resumable flow, an outbox, or reordering so
irreversible external calls happen last.

### 4. mem0 deletion failure is silent

`app/agents/shared/memory/factory.py:104` catches and logs, then returns
normally. Erasure reports success while the extracted-fact memories remain.

Contrast with `delete_conversation_checkpoints`, which propagates. The two
erasure steps have opposite failure semantics for no stated reason — and on the
webhook path the difference is load-bearing: only the propagating step earns
an svix redelivery.

### 5. Logs retain both identifiers with no retention policy

`app/api/middlewares/logging.py:40` binds `clerk_id`; `user_id` is bound after
provisioning. Every structured log line carries them. Nothing documents a
retention period, and erasure does not touch log storage.

Standard practice is a documented, time-limited retention — but it has to be
written down to count.

### 6. `anonymous_id` uses only 32 bits of the UUID

`app/models/user.py:55` — `f"deleted_user_{self.id[:8]}"` feeds two `unique=True`
columns (`clerk_id`, `email`). Birthday collision at ~65k anonymised users, at
which point a second erasure raises `IntegrityError`.

Negligible at this product's scale, and not a compliance issue — but using the
full UUID costs nothing.

### 7. Backups are unaddressed

No policy documented for erasure propagation into DB backups. Defensible with a
documented rolling-window policy; currently there is no policy at all.

### 8. Erasure volume at consumer scale

A B2C product gets erasure requests at a rate that makes the manual/partial-failure
posture in finding 3 untenable. This likely needs to be a queued, retryable job rather
than an inline request handler as adoption grows.

---

## Resolving the retained `user.id`

The blocker for hard delete is `conversation.user_id`: NOT NULL, and its FK carries no
`ondelete` clause (`alembic/versions/20260915_1321_a620e3481aa3_initial_schema.py:53-56`).
A `DELETE FROM "user"` raises `ForeignKeyViolation` today.

Five patterns are in production use:

| Pattern | Mechanism | Fits when |
|---|---|---|
| **Cascade** | `ON DELETE CASCADE` | Child rows have no value without the user |
| **Orphan** | nullable FK + `ON DELETE SET NULL` | Row needed for counts, owner is not |
| **Shared sentinel** | One "ghost" user row; all children repoint to it | Content must survive, author must not (GitHub `ghost`, Reddit `[deleted]`) |
| **PII vault** | All PII in one table; everything else holds an opaque id | Erasure = delete one vault row. Common in fintech/healthcare |
| **Crypto-shredding** | Per-user encryption key; destroy the key | Immutable stores, event logs, **backups** (see finding 7) |

### The key correction to the current design

**A production tombstone is *shared*, not per-person.**

`anonymize_user()` mints a new tombstone *per erased individual*, which is k=1 —
it singles out. GitHub's ghost user is **one row shared by everyone who ever
deleted an account**, so it is k=N and singles out nobody. Identical
"keep the FK valid" goal, opposite privacy outcome.

The fix is therefore not a better `anonymous_id` (finding 6) — it is not minting one per
person. Repointing `conversation.user_id` at a single shared ghost row keeps
every conversation row for analytics while removing both the per-person key and
the grouping that made those rows mutually linkable.

---

## Analytics and ML training

Recorded because the instinct to retain conversations for training is what makes
this ticket wider than it looks.

**Retaining conversation rows buys nothing trainable.** A `Conversation` row is
`id`, `user_id`, `name`, and timestamps (`app/models/conversation.py:41-50`). The
messages are in the LangGraph checkpoint tables keyed by `thread_id`, hard-deleted
in `erase_user` (`app/services/user/service.py:106`); `name` is cleared at the same
step. A post-erasure row contains no text. Keeping it buys a row count and costs a
retained per-person activity series.

**Training on a departed user's content is the thing Art 17 blocks.**

- Training is usually a *different purpose* from service delivery (Art 5(1)(b)),
  so it needs its own lawful basis and disclosure, established **up front**. It
  cannot be discovered at deletion time. Consent withdrawn → Art 17(1)(b) →
  erase. Legitimate interest → a departed user's Art 21 objection generally wins.
- **Already-trained models** generally need not be retrained, but EDPB Opinion
  28/2024 holds a model can itself contain personal data where it memorises and
  can regurgitate, and that unlawful training data can taint the model.
- **Truly anonymised data is out of scope** (Recital 26) — but free-text queries
  and posts resist anonymisation. Stripping `user_id` is nowhere near enough
  (cf. AOL 2006 search logs, Netflix Prize). Aggregates are genuinely fine.
- **Art 17(3)(d) statistical/research purposes** is narrower than it sounds:
  Recital 162 requires aggregate results *not used for measures or decisions
  regarding particular individuals*, which excludes analytics feeding
  personalisation.

**The architecture that delivers it:** build a de-identified training corpus
**at ingestion**, with its own lawful basis and disclosure, so erasure never
touches it. Retrofitting de-identification at deletion time does not work. This
is a separate design decision and does not belong in the erasure flow.

Note `mem0` extracts *facts about the user* — profiling, unambiguously personal
data, not salvageable as "analytics."

---

## Design options (not decided)

Recorded so a future spec starts from a shortlist rather than a blank page.

| Option | Shape | Trade-off |
|---|---|---|
| **1. Hard delete, aggregate first** | Increment counters in a non-personal stats table, then cascade-delete the `user` row and its `conversation` rows | Genuinely stops being personal data. Needs the stats table first. Destroys nothing trainable — there is no content in those rows |
| **2. Shared sentinel** | Repoint `conversation.user_id` at one ghost user; delete the real `user` row | Keeps every row for analytics *and* de-identifies. Best fit if "keep the rows" is firm |
| **3. Keep pseudonymised, justify it** | Stop calling it anonymisation. Document the Art 17(3) basis per retained field, add a retention window ending in hard delete | Honest and low-churn, but requires a legal basis that today does not exist |

Options 1 and 2 compose with a role check if admin accounts ever need different
handling (e.g. retaining an admin's actions for audit under a different basis) — that
is a real possibility now that `role` exists, but nothing today suggests it is needed.

**Note:** whichever is chosen, finding 2 (Langfuse) must be solved independently. No
change to the DB row affects it.

---

## Open questions for a future spec

1. Does Langfuse retention get solved by deletion-on-erasure, by masking content
   at source, or by not sending `langfuse_user_id` at all?
2. What is the log retention window, and who enforces it?
3. Does finding 3 justify an outbox/job queue, or is reordering the external calls enough?
4. Is a de-identified training corpus wanted at all? If yes it needs a lawful
   basis, a privacy-policy disclosure, and an ingestion-time pipeline — none of
   which belong in the erasure flow. If no, say so explicitly so the question
   stops resurfacing.
5. Are conversation rows actually wanted post-erasure? They hold no content, so
   the honest answer may be no — which collapses option 2 into option 1.

---

## Verification notes

Findings re-read from source on 2026-09-15 against the current B2C codebase. Anchors
cited:

- `app/models/user.py:39-66` — `User` fields, `anonymize_user()`
- `app/models/conversation.py:41-50` — retained FK
- `app/api/v1/auth.py:51-76` — `delete_me` five-step flow
- `app/agents/shared/observability/langfuse.py:23-37` — trace metadata
- `app/agents/shared/memory/factory.py:98-105` — swallowed exception
- `app/agents/shared/checkpointing/postgres.py:93` — checkpoint deletion (propagates)
- `app/api/middlewares/logging.py:37-40` — identifier binding
- `alembic/versions/20260915_1321_a620e3481aa3_initial_schema.py:53-56` — no `ondelete` on `conversation.user_id`

`grep -rn "mask" app/` returns nothing — no Langfuse content masking.
