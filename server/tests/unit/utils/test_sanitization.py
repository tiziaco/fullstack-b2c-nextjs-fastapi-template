"""Tests for app.utils.sanitization — XSS prevention, email validation, password strength."""

import pytest

from app.exceptions.base import ValidationError
from app.utils.sanitization import (
    sanitize_dict,
    sanitize_email,
    sanitize_list,
    sanitize_string,
)

pytestmark = pytest.mark.unit


class TestSanitizeString:
    """Tests for sanitize_string()."""

    def test_normal_text_passes_through(self):
        assert sanitize_string("Hello World") == "Hello World"

    def test_empty_string(self):
        assert sanitize_string("") == ""

    def test_whitespace_preserved(self):
        assert sanitize_string("  hello  ") == "  hello  "

    def test_html_angle_brackets_escaped(self):
        result = sanitize_string("<b>bold</b>")
        assert "<b>" not in result
        assert "&lt;b&gt;" in result

    def test_script_tags_removed(self):
        result = sanitize_string("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "alert" not in result

    def test_null_bytes_removed(self):
        result = sanitize_string("hello\0world")
        assert "\0" not in result
        assert "helloworld" in result

    def test_non_string_input_converted(self):
        result = sanitize_string(12345)
        assert result == "12345"


class TestSanitizeEmail:
    """Tests for sanitize_email()."""

    def test_valid_email_lowercased(self):
        assert sanitize_email("User@Example.COM") == "user@example.com"

    def test_valid_email_with_dots(self):
        assert sanitize_email("first.last@domain.co.uk") == "first.last@domain.co.uk"

    def test_invalid_email_no_at(self):
        with pytest.raises(ValidationError, match="Invalid email format"):
            sanitize_email("not-an-email")

    def test_invalid_email_no_domain(self):
        with pytest.raises(ValidationError, match="Invalid email format"):
            sanitize_email("user@")

    def test_invalid_email_no_tld(self):
        with pytest.raises(ValidationError, match="Invalid email format"):
            sanitize_email("user@domain")


class TestSanitizeDict:
    """Tests for sanitize_dict()."""

    def test_string_values_sanitized(self):
        result = sanitize_dict({"name": "<script>x</script>"})
        assert "<script>" not in result["name"]

    def test_non_string_values_preserved(self):
        result = sanitize_dict({"count": 42, "active": True, "data": None})
        assert result == {"count": 42, "active": True, "data": None}

    def test_nested_dict_recursion(self):
        data = {"outer": {"inner": "<b>bold</b>"}}
        result = sanitize_dict(data)
        assert "&lt;b&gt;" in result["outer"]["inner"]

    def test_nested_list_in_dict(self):
        data = {"items": ["<b>one</b>", "two"]}
        result = sanitize_dict(data)
        assert "&lt;b&gt;" in result["items"][0]
        assert result["items"][1] == "two"


class TestSanitizeList:
    """Tests for sanitize_list()."""

    def test_string_items_sanitized(self):
        result = sanitize_list(["<script>x</script>", "safe"])
        assert "<script>" not in result[0]
        assert result[1] == "safe"

    def test_non_string_items_preserved(self):
        result = sanitize_list([1, True, None])
        assert result == [1, True, None]

    def test_nested_dict_in_list(self):
        result = sanitize_list([{"key": "<b>val</b>"}])
        assert "&lt;b&gt;" in result[0]["key"]
