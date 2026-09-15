"""Unit tests for model mixins and User.anonymize_user().

These tests exercise pure in-memory behaviour — no database required.
"""

import pytest

from app.models.conversation import Conversation
from app.models.user import User

pytestmark = pytest.mark.unit


# ============================================================================
# SoftDeleteMixin (tested via Conversation)
# ============================================================================


class TestSoftDeleteMixin:
    """Tests for SoftDeleteMixin properties and methods."""

    def test_is_deleted_false_by_default(self):
        conv = Conversation(id="conv-1", user_id="user-1")
        assert conv.is_deleted is False

    def test_deleted_at_none_by_default(self):
        conv = Conversation(id="conv-1", user_id="user-1")
        assert conv.deleted_at is None

    def test_soft_delete_sets_deleted_at(self):
        conv = Conversation(id="conv-1", user_id="user-1")
        conv.soft_delete()
        assert conv.deleted_at is not None

    def test_is_deleted_true_after_soft_delete(self):
        conv = Conversation(id="conv-1", user_id="user-1")
        conv.soft_delete()
        assert conv.is_deleted is True

    def test_restore_clears_deleted_at(self):
        conv = Conversation(id="conv-1", user_id="user-1")
        conv.soft_delete()
        conv.restore()
        assert conv.deleted_at is None

    def test_is_deleted_false_after_restore(self):
        conv = Conversation(id="conv-1", user_id="user-1")
        conv.soft_delete()
        conv.restore()
        assert conv.is_deleted is False


# ============================================================================
# AnonymizableMixin (tested via User)
# ============================================================================


class TestAnonymizableMixin:
    """Tests for AnonymizableMixin properties and methods."""

    def test_is_anonymized_false_by_default(self):
        user = User(clerk_id="clerk_1", email="u@example.com")
        assert user.is_anonymized is False

    def test_anonymized_at_none_by_default(self):
        user = User(clerk_id="clerk_1", email="u@example.com")
        assert user.anonymized_at is None

    def test_mark_anonymized_sets_anonymized_at(self):
        user = User(clerk_id="clerk_1", email="u@example.com")
        user.mark_anonymized()
        assert user.anonymized_at is not None

    def test_is_anonymized_true_after_mark_anonymized(self):
        user = User(clerk_id="clerk_1", email="u@example.com")
        user.mark_anonymized()
        assert user.is_anonymized is True


# ============================================================================
# User.anonymize_user
# ============================================================================


class TestUserAnonymizeUser:
    """Tests for User.anonymize_user() GDPR anonymization method."""

    @pytest.fixture
    def full_user(self):
        return User(
            clerk_id="clerk_abc123",
            email="alice@example.com",
            first_name="Alice",
            last_name="Smith",
            avatar_url="https://example.com/avatar.jpg",
            email_verified=True,
        )

    def test_clerk_id_replaced(self, full_user):
        full_user.anonymize_user()
        assert full_user.clerk_id != "clerk_abc123"
        assert full_user.clerk_id.startswith("deleted_user_")

    def test_email_replaced_with_anonymized_local(self, full_user):
        full_user.anonymize_user()
        assert full_user.email.endswith("@anonymized.local")

    def test_first_name_cleared(self, full_user):
        full_user.anonymize_user()
        assert full_user.first_name is None

    def test_last_name_cleared(self, full_user):
        full_user.anonymize_user()
        assert full_user.last_name is None

    def test_avatar_url_cleared(self, full_user):
        full_user.anonymize_user()
        assert full_user.avatar_url is None

    def test_email_verified_set_to_false(self, full_user):
        full_user.anonymize_user()
        assert full_user.email_verified is False

    def test_is_anonymized_true_after_call(self, full_user):
        full_user.anonymize_user()
        assert full_user.is_anonymized is True

    def test_conversation_names_cleared(self, full_user):
        full_user.conversations = [
            Conversation(id="conv-1", user_id="any", name="Project Alpha"),
            Conversation(id="conv-2", user_id="any", name="My ideas"),
        ]
        full_user.anonymize_user()
        assert full_user.conversations[0].name == ""
        assert full_user.conversations[1].name == ""

    def test_no_conversations_does_not_raise(self, full_user):
        full_user.conversations = []
        full_user.anonymize_user()  # Should not raise
        assert full_user.is_anonymized is True
