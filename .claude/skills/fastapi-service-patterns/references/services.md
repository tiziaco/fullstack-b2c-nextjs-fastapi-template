# Service Classes

Services are **stateless orchestrators**: they hold no state and no direct DB access. All database work lives in a
**repository** — the service calls it, plus any external API client wrappers (see `references/client-wrappers.md`),
and composes the result. Both a service and its repository are stateless classes with `@staticmethod async` methods,
each exporting a **module-level singleton**.

## Basic case: one repository

```python
# app/services/payment/repository.py

class PaymentRepository:
    """DB operations for payments."""

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: str, payment_id: int) -> Optional[Payment]:
        stmt = select(Payment).where(
            Payment.id == payment_id,
            Payment.user_id == user_id,
            Payment.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, user_id: str, data: dict) -> Payment:
        payment = Payment(user_id=user_id, **data)
        db.add(payment)
        await db.flush()
        await db.refresh(payment)
        logger.info("payment_created", user_id=user_id, payment_id=payment.id)
        return payment

    @staticmethod
    async def update(db: AsyncSession, payment: Payment, **fields) -> Payment:
        for field, value in fields.items():
            setattr(payment, field, value)
        await db.flush()
        await db.refresh(payment)
        logger.info("payment_updated", payment_id=payment.id, fields=list(fields))
        return payment

    @staticmethod
    async def delete(db: AsyncSession, payment: Payment) -> None:
        payment.deleted_at = datetime.now(timezone.utc)
        await db.flush()
        logger.info("payment_deleted", payment_id=payment.id)

    @staticmethod
    async def list(
        db: AsyncSession, user_id: str, filters: PaymentFilters, offset: int, limit: int
    ) -> tuple[list[Payment], int]:
        stmt = (
            select(Payment)
            .where(Payment.user_id == user_id, Payment.deleted_at.is_(None))
            .offset(offset)
            .limit(limit)
        )
        # Apply filters here...
        result = await db.execute(stmt)
        items = list(result.scalars().all())

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar_one()

        return items, total


payment_repository = PaymentRepository()
```

```python
# app/services/payment/service.py

class PaymentService:
    """Orchestrates payment operations. Holds no DB or HTTP logic of its own —
    that lives in payment_repository / stripe_service."""

    @staticmethod
    async def get(db: AsyncSession, user_id: str, payment_id: int) -> Payment:
        payment = await payment_repository.get_by_id(db, user_id, payment_id)
        if not payment:
            raise PaymentNotFoundError(f"Payment {payment_id} not found", payment_id=payment_id)
        return payment

    @staticmethod
    async def create(db: AsyncSession, user_id: str, data: PaymentCreate) -> Payment:
        return await payment_repository.create(db, user_id, data.model_dump())

    @staticmethod
    async def update(db: AsyncSession, user_id: str, payment_id: int, data: PaymentUpdate) -> Payment:
        payment = await PaymentService.get(db, user_id, payment_id)
        update_fields = data.model_dump(exclude_unset=True)  # Only provided fields
        return await payment_repository.update(db, payment, **update_fields)

    @staticmethod
    async def delete(db: AsyncSession, user_id: str, payment_id: int) -> None:
        payment = await PaymentService.get(db, user_id, payment_id)
        await payment_repository.delete(db, payment)

    @staticmethod
    async def list(
        db: AsyncSession, user_id: str, filters: PaymentFilters, offset: int, limit: int
    ) -> tuple[list[Payment], int]:
        return await payment_repository.list(db, user_id, filters, offset, limit)


# Singleton — import and use this, don't re-instantiate in routes
payment_service = PaymentService()
```

## Orchestrating multiple collaborators

A service is not limited to one repository. Its job is to coordinate whatever the flow needs — one or more
repositories, an external API client wrapper (`references/client-wrappers.md`), a cache — and stay the only place
that knows how they fit together. Route handlers and repositories never call each other directly.

Real example from this codebase: `UserService.resolve_user()` coordinates `user_repository` (DB) and `clerk_client`
(external API client wrapper) in a single JIT-provisioning flow — none of that DB or HTTP logic lives in the
service itself.

A payment checkout follows the same shape — charge via the external client, then persist the result:

```python
# app/services/payment/service.py

class PaymentService:
    @staticmethod
    async def checkout(db: AsyncSession, user_id: str, data: CheckoutCreate) -> Payment:
        charge = stripe_service.create_charge(
            customer_id=data.stripe_customer_id,
            amount=data.amount,
        )
        payment = await payment_repository.create(
            db,
            user_id,
            {"amount": data.amount, "status": charge.status, "stripe_charge_id": charge.id},
        )
        logger.info("payment_checkout_completed", user_id=user_id, payment_id=payment.id, charge_id=charge.id)
        return payment
```

`stripe_service.create_charge` is a sync SDK call — wrap it in `asyncio.to_thread()` at the call site if the
underlying client is synchronous (see `references/client-wrappers.md`).

## Rules

- Services orchestrate; they never call `db.execute()`/`select()` directly — that lives in the repository
- A service may depend on more than one repository and/or external client wrapper — orchestration across
  collaborators is the point of the service layer
- Repositories never call other repositories, external clients, or each other's service — keep them one level below
- All methods (service and repository) are `@staticmethod` and `async` — no state on either class
- Parameter order: `db` first, then `user_id`, then domain params/data
- `flush()` + `refresh()` after writes — never `commit()` (the `get_db_session` dependency commits)
- Soft-delete: set `deleted_at = datetime.now(timezone.utc)`, never issue a `DELETE`
- Soft-delete queries always filter `deleted_at.is_(None)`
- PATCH updates use `model_dump(exclude_unset=True)` — only write fields the caller actually sent
- Log significant mutations with structured key=value pairs (`logger.info`, `logger.warning`)
- Never return `None` — raise a domain exception if the resource doesn't exist
