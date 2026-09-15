# GDPR Compliance Guide for B2C Applications

> **Open findings.** A review of the implemented erasure flow found gaps this
> guide does not cover — most importantly that Langfuse retains message content
> keyed by the `user.id` that survives erasure. See
> [`gdpr-erasure-findings.md`](./gdpr-erasure-findings.md).

## Overview

For B2C applications serving European users, GDPR (General Data Protection Regulation) compliance is **mandatory**, not optional. This guide explains how to handle user data deletion properly.

## Key GDPR Principle: Right to Erasure (Article 17)

When a user requests account deletion, you must **actually delete** their personal data, not just hide it.

### ❌ What is NOT Compliant

```python
# WRONG: Soft delete user data
user.soft_delete()
await session.commit()
# User's email, name, etc. are still in your database!
```

### ✅ What IS Compliant

1. **Anonymize personal data** - Replace with generic values
2. **Hard delete sensitive content** - Remove chat messages, files, etc.
3. **Keep business records** - Non-personal metadata for legal compliance

## Data Classification

### Personal Data (Must Delete/Anonymize)
- ✅ Name, email, phone number
- ✅ Profile pictures, avatars
- ✅ IP addresses, device IDs
- ✅ Chat messages, user-generated content
- ✅ Behavioral data (browsing history, preferences)
- ✅ Any data that can identify an individual

### Business Records (Can Keep)
- ✅ Anonymized analytics (e.g., "X users signed up on date Y")
- ✅ Aggregated statistics (no individual identification)
- ✅ Transaction records required by law (tax, accounting)
- ✅ Fraud prevention data (time-limited, proportionate)
- ✅ System logs (if anonymized)

## Implementation Pattern

### 1. User Model (Anonymization)

```python
from app.models.base import BaseModel, AnonymizableMixin


class User(BaseModel, AnonymizableMixin, table=True):
    id: str = Field(primary_key=True)
    clerk_id: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]

    def anonymize_user(self) -> None:
        """Clear all personal identifiable information."""
        anonymous_id = f"deleted_user_{self.id[:8]}"
        self.clerk_id = anonymous_id
        self.email = f"{anonymous_id}@anonymized.local"
        self.first_name = None
        self.last_name = None
        self.avatar_url = None
        self.mark_anonymized()
```

> **Terminology caution.** The end state is strong *pseudonymisation*, not
> anonymisation: the row keeps its `id`, still referenced by
> `Conversation.user_id`, so records remain linkable. The EDPB's 2025
> Coordinated Enforcement Action on the right to erasure specifically
> criticised controllers who present this as anonymisation. Do not claim
> anonymisation in compliance documentation without a fuller review.

### 2. GDPR-Compliant Deletion Service

```python
# app/services/user/api.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.user import User
from app.models.conversation import Conversation


async def delete_user_gdpr_compliant(
    user_id: str,
    session: AsyncSession,
    checkpointer: AsyncPostgresSaver,  # LangGraph checkpointer
) -> None:
    """Delete user account in GDPR-compliant manner.

    Steps:
    1. Hard delete all chat messages from LangGraph checkpointing
    2. Soft delete conversation metadata
    3. Anonymize user personal data
    4. Log deletion for audit trail

    Args:
        user_id: ID of user to delete
        session: Database session
        checkpointer: LangGraph checkpointer for message storage

    Raises:
        UserNotFoundError: If user doesn't exist
    """
    # 1. Get user
    stmt = select(User).where(User.id == user_id)
    result = await session.exec(stmt)
    user = result.first()

    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    if user.is_anonymized:
        # Already deleted
        return

    # 2. Hard delete all chat messages from LangGraph checkpointing
    # This is the actual user content that MUST be deleted
    stmt = select(Conversation).where(Conversation.user_id == user_id, Conversation.deleted_at.is_(None))
    result = await session.exec(stmt)
    conversations = result.all()  # Materialise before iterating

    for conv in conversations:
        # Delete all messages for this conversation from LangGraph
        # LangGraph stores in 'checkpoints' and 'writes' tables
        try:
            # Clear checkpoint history (messages are stored here)
            await checkpointer.delete_thread(conv.id)
        except Exception as e:
            logger.error("failed_to_delete_conversation_messages", conversation_id=conv.id, error=str(e))
            # Continue with deletion even if checkpointer fails

        # Soft delete conversation metadata (non-personal)
        conv.soft_delete()

    # 3. Anonymize user personal data (also clears conversation names)
    user.anonymize_user()

    # 4. Commit all changes
    await session.commit()

    # 5. Log for audit trail (anonymized)
    logger.info(
        "user_erased",
        user_id=user_id,
        conversation_count=len(conversations),
        anonymized_at=user.anonymized_at.isoformat(),
    )
```

### 3. API Endpoint

```python
# app/api/routes/user.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies.database import get_session
from app.api.dependencies.auth import get_current_user
from app.services.user.api import delete_user_gdpr_compliant

router = APIRouter()


@router.delete("/me")
async def delete_my_account(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    checkpointer: AsyncPostgresSaver = Depends(get_checkpointer),
):
    """Delete current user's account (GDPR compliant).

    This will:
    - Permanently delete all chat messages
    - Anonymize personal information
    - Keep anonymized business records for compliance

    This action cannot be undone.
    """
    await delete_user_gdpr_compliant(user_id=current_user.id, session=session, checkpointer=checkpointer)

    return {"message": "Account deleted successfully"}
```

## What You Can Keep (Legal Bases)

### 1. Legal Obligation (GDPR Article 17.3.b)

**Tax & Accounting Records** - Keep for legally required period:
- EU: Typically 7-10 years (varies by country)
- Must be anonymized where possible
- Document the legal basis

```python
# Keep transaction metadata for tax compliance
class Transaction(BaseModel, table=True):
    id: str
    user_id: str  # Can remain after user anonymization
    amount: float
    tax_amount: float
    transaction_date: datetime
    # Purpose: Tax compliance (7 years retention in Germany)
```

### 2. Legal Claims (GDPR Article 17.3.e)

**Fraud Prevention** - Keep data if:
- User previously committed fraud
- Active legal proceedings
- Must be proportionate and time-limited
- Document specific reason

```python
class FraudRecord(BaseModel, table=True):
    id: str
    user_id: str
    incident_date: datetime
    description: str
    retention_until: datetime  # Maximum 5 years
    legal_basis: str  # "Fraud prevention - Article 17.3.e"
```

### 3. Anonymized Data (Not Personal Data)

**Analytics** - Aggregate, non-identifiable statistics:

```python
# ✅ OK: Aggregated daily statistics
{"date": "2026-02-18", "new_users": 150, "total_conversations": 1200}

# ❌ NOT OK: Individual tracking
{"user_id": "123", "login_count": 50, "last_login": "2026-02-18"}
```

## Data Retention Policy

Create a documented retention policy:

```python
# config/retention_policy.py
from datetime import timedelta

RETENTION_POLICY = {
    "user_personal_data": {
        "retention": "Until user requests deletion",
        "after_deletion": "Anonymized immediately",
    },
    "chat_messages": {
        "retention": "Until user requests deletion",
        "after_deletion": "Hard deleted immediately",
    },
    "transaction_records": {
        "retention": "7 years (German tax law)",
        "after_deletion": "Anonymized (keep amount, date, but not PII)",
    },
    "fraud_records": {
        "retention": "5 years maximum",
        "after_deletion": "Hard deleted after retention period",
    },
    "anonymized_analytics": {
        "retention": "Indefinitely (not personal data)",
        "after_deletion": "N/A",
    },
}
```

## Common Mistakes to Avoid

### ❌ Mistake 1: Using Soft Delete for User Data
```python
# WRONG
user.soft_delete()  # Email still in database!
```

### ❌ Mistake 2: Keeping Data "Just in Case"
```python
# WRONG - No legal basis
await session.delete(user)  # But keep backup "for analytics"
```

### ❌ Mistake 3: Not Deleting Related Data
```python
# WRONG - Delete user but forget messages
user.anonymize_user()
# Forgot to delete chat messages! Still has personal data.
```

### ❌ Mistake 4: Indefinite Retention
```python
# WRONG - Even for legal compliance, must have end date
class AuditLog(BaseModel, table=True):
    retention_until = None  # Infinite retention not allowed
```

## Compliance Checklist

Before launching your B2C app:

- [ ] **User Deletion Endpoint** - Users can delete their account
- [ ] **Hard Delete Messages** - Chat history completely removed
- [ ] **Anonymize User Records** - PII replaced with generic values
- [ ] **Cascade Deletion** - All related personal data removed
- [ ] **Data Retention Policy** - Documented with legal bases
- [ ] **Maximum Retention Periods** - Even for legal data
- [ ] **Audit Logging** - Log deletions (anonymized)
- [ ] **Privacy Policy** - Explain data handling to users
- [ ] **DPO Contact** - Data Protection Officer for large operations
- [ ] **GDPR Rights** - Access, portability, rectification implemented

## Testing Your Implementation

```python
# tests/test_gdpr_compliance.py
async def test_user_deletion_removes_all_personal_data(session):
    """Verify GDPR-compliant deletion removes PII."""
    # Create user
    user = User(email="test@example.com", first_name="John")
    session.add(user)
    await session.commit()
    
    # Delete user
    await delete_user_gdpr_compliant(user.id, session, checkpointer)
    
    # Verify anonymization
    await session.refresh(user)
    assert user.is_anonymized
    assert "deleted_user_" in user.email
    assert user.first_name is None
    
    # Verify no personal data remains
    # Check messages are gone, etc.
```

## When in Doubt

1. **Consult a lawyer** - GDPR fines can be up to €20M or 4% of revenue
2. **Delete more rather than less** - Err on the side of user privacy
3. **Document everything** - Why you keep what you keep
4. **Set expiry dates** - Even legal data has limits
5. **Be transparent** - Tell users what you do with their data

## Resources

- **GDPR Full Text**: https://gdpr-info.eu/
- **Article 17 (Right to Erasure)**: https://gdpr-info.eu/art-17-gdpr/
- **EU Data Protection Board**: https://edpb.europa.eu/
- **GDPR Developer Guide**: https://gdpr.eu/developers/

## Summary

For B2C applications in Europe:

✅ **Use anonymization** for user personal data (not soft delete)  
✅ **Hard delete** user-generated content (messages, files)  
✅ **Keep business records** only with documented legal basis  
✅ **Set retention limits** on all data, even legal compliance data  
✅ **Be transparent** about what you keep and why  

Your users have the right to be forgotten - respect it.
