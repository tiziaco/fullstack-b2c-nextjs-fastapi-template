# API Routes

## Dependencies

Use the project's type aliases to keep endpoint signatures clean:

```python
from app.api.dependencies.auth import CurrentUser
from app.api.dependencies.database import DbSession
```

## Route structure

```python
# app/api/v1/payments.py

router = APIRouter(prefix="/payments", tags=["payments"])

@router.post("", response_model=PaymentResponse, status_code=201)
@limiter.limit("10/minute")
async def create_payment(
    request: Request,       # Always first — required by the rate limiter
    body: PaymentCreate,
    db: DbSession,
    user: CurrentUser,
) -> PaymentResponse:
    payment = await payment_service.create(db, user.id, body)
    return PaymentResponse.model_validate(payment)


@router.get("/{payment_id}", response_model=PaymentResponse)
@limiter.limit("120/minute")
async def get_payment(
    request: Request,
    payment_id: int,
    db: DbSession,
    user: CurrentUser,
) -> PaymentResponse:
    payment = await payment_service.get(db, user.id, payment_id)
    return PaymentResponse.model_validate(payment)


@router.patch("/{payment_id}", response_model=PaymentResponse)
@limiter.limit("60/minute")
async def update_payment(
    request: Request,
    payment_id: int,
    body: PaymentUpdate,
    db: DbSession,
    user: CurrentUser,
) -> PaymentResponse:
    payment = await payment_service.update(db, user.id, payment_id, body)
    return PaymentResponse.model_validate(payment)


@router.delete("/{payment_id}", status_code=204)
@limiter.limit("60/minute")
async def delete_payment(
    request: Request,
    payment_id: int,
    db: DbSession,
    user: CurrentUser,
) -> None:
    await payment_service.delete(db, user.id, payment_id)
```

Rules:
- `request: Request` is always first
- `db: DbSession` and `user: CurrentUser` come after path/body params
- Use `model_validate(orm_object)` to convert ORM models (requires `model_config = {"from_attributes": True}` on the schema)
- Deletes: `status_code=204`, return type `-> None`, no response body
- Apply `@limiter.limit(...)` on every route

## Input validation (fail fast)

Validate at the route level before calling any service:

```python
if not file.filename or not file.filename.endswith(".csv"):
    raise HTTPException(status_code=422, detail="Only .csv files are accepted.")

if len(df) > settings.CSV_MAX_ROWS:
    raise HTTPException(
        status_code=422,
        detail=f"CSV exceeds the {settings.CSV_MAX_ROWS}-row limit ({len(df)} rows).",
    )
```

## Pagination

Use offset/limit. Return an envelope with `items`, `total`, `offset`, `limit`.

```python
class PaymentListResponse(BaseModel):
    items: List[PaymentResponse]
    total: int
    offset: int
    limit: int

@router.get("", response_model=PaymentListResponse)
@limiter.limit("120/minute")
async def list_payments(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    filters: PaymentFilters = Depends(),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),  # Always cap the max
) -> PaymentListResponse:
    payments, total = await payment_service.list(db, user.id, filters, offset, limit)
    return PaymentListResponse(
        items=[PaymentResponse.model_validate(p) for p in payments],
        total=total,
        offset=offset,
        limit=limit,
    )
```

Group filter query params into a `Depends()` class:

```python
class PaymentFilters(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    date_from: Optional[date] = Query(None)
    date_to: Optional[date] = Query(None)
    status: Optional[str] = Query(None)
```

## Batch operations

Named paths like `/batch` must be declared **before** `/{payment_id}` — otherwise FastAPI tries to parse `"batch"` as an integer ID.

```python
class BatchDeleteRequest(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=100)

class BatchDeleteResponse(BaseModel):
    deleted: int

# Declared before /{payment_id}
@router.delete("/batch", response_model=BatchDeleteResponse)
@limiter.limit("30/minute")
async def batch_delete_payments(
    request: Request,
    body: BatchDeleteRequest,
    db: DbSession,
    user: CurrentUser,
) -> BatchDeleteResponse:
    count = await payment_service.batch_delete(db, user.id, body.ids)
    return BatchDeleteResponse(deleted=count)
```

Batch operations should be all-or-nothing: if any item fails, the entire batch rolls back.

## Response schemas

```python
class PaymentResponse(BaseModel):
    id: int
    amount: Decimal = Field(..., description="Payment amount")
    status: str = Field(..., description="Payment status")
    created_at: datetime

    model_config = {"from_attributes": True}
```
