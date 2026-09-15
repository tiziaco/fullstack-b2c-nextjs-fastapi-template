# Database Operations

All patterns below belong in the domain's `repository.py`, never in `service.py` — see `references/services.md`.

## Querying: `select()` vs `session.get()`

Always use `select()` with explicit `WHERE` clauses. `session.get()` is a raw PK lookup that bypasses all filters — it will return soft-deleted records and records belonging to other users.

```python
# Good — user-scoped, soft-delete aware
stmt = select(Payment).where(
    Payment.id == payment_id,
    Payment.user_id == user_id,
    Payment.deleted_at.is_(None),
)
result = await db.execute(stmt)
payment = result.scalar_one_or_none()

# Bad — bypasses user scoping and soft-delete filter
payment = await db.get(Payment, payment_id)
```

`session.get()` is only appropriate when you genuinely need a raw PK lookup with no additional constraints (e.g., internal admin operations).

Use `scalar_one_or_none()` when the record may not exist (handle the None case). Use `scalar_one()` only when you're certain the record exists and want an exception if it doesn't.

---

## Bulk Operations (Avoid N+1)

Never fetch or mutate records one at a time in a loop. Fetch all in a single `WHERE id IN (...)` query, then mutate in bulk.

```python
# Bad — N queries for N items
for item_id in ids:
    item = await db.get(Payment, item_id)  # 1 query per item
    item.deleted_at = now

# Good — 1 query for all items
stmt = select(Payment).where(
    Payment.id.in_(ids),
    Payment.user_id == user_id,
    Payment.deleted_at.is_(None),
)
result = await db.execute(stmt)
payments = result.scalars().all()

# Validate all IDs were found before mutating
found_ids = {p.id for p in payments}
missing = set(ids) - found_ids
if missing:
    raise PaymentNotFoundError(
        f"Payments not found: {missing}",
        missing_ids=list(missing),
    )

now = datetime.now(timezone.utc)
for payment in payments:
    payment.deleted_at = now

await db.flush()
```

For large batch updates, prefer a single `UPDATE ... WHERE id IN (...)` statement over loading all records into memory:

```python
from sqlalchemy import update

stmt = (
    update(Payment)
    .where(Payment.id.in_(ids), Payment.user_id == user_id)
    .values(deleted_at=datetime.now(timezone.utc))
    .execution_options(synchronize_session="fetch")
)
await db.execute(stmt)
```

---

## Relationship Loading (Avoid MissingGreenlet)

Lazy loading is disabled in async SQLAlchemy — accessing an unloaded relationship raises `MissingGreenlet`. Always load relationships explicitly.

**`selectinload`** — use for one-to-many / many-to-many. Issues a second `SELECT ... WHERE id IN (...)` query.

```python
from sqlalchemy.orm import selectinload

stmt = (
    select(User)
    .where(User.id == user_id)
    .options(selectinload(User.conversations))
)
result = await db.execute(stmt)
user = result.scalar_one_or_none()
# user.conversations is now safe to access
```

**`joinedload`** — use for many-to-one / one-to-one. Issues a single `JOIN` query. Avoid for collections — it produces duplicate rows.

```python
from sqlalchemy.orm import joinedload

stmt = (
    select(Transaction)
    .where(Transaction.id == transaction_id)
    .options(joinedload(Transaction.category))
)
```

**Rule**: if a repository method accesses a relationship, it must eagerly load it in the same query. Don't rely on the caller to pre-load it — that's fragile and breaks when the method is called from a different context.

---

## Database Error Handling

`get_db_session` translates SQLAlchemy errors automatically — don't re-catch them in repository or service code:

- `IntegrityError` → `DatabaseConflictError` (409)
- `OperationalError` → `DatabaseConnectionError` (503)
- `DBAPIError` → `DatabaseError` (500)

The one valid exception is resolving a **race condition** on insert, where you re-query after rollback:

```python
try:
    record = await repository.create(session, data)
except IntegrityError:
    await session.rollback()
    logger.info("race_condition_resolved", key=unique_key)
    record = await repository.get_by_unique_key(session, unique_key)
    if not record:
        raise RuntimeError(f"Failed to resolve race condition for {unique_key}")
```

---

## Count Queries

When you need both a page of results and a total count, run the count against a subquery of the filtered statement — don't run two separate queries with duplicated filter logic.

```python
stmt = (
    select(Payment)
    .where(Payment.user_id == user_id, Payment.deleted_at.is_(None))
    # apply filters here...
    .offset(offset)
    .limit(limit)
)
result = await db.execute(stmt)
items = list(result.scalars().all())

count_stmt = select(func.count()).select_from(
    stmt.order_by(None).limit(None).offset(None).subquery()
)
total = (await db.execute(count_stmt)).scalar_one()
```
