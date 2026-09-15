"""The Rust extension behind the search tool logs through Python's logging.

`ddgs` calls into `primp`, which is compiled with pyo3-log: records from the
Rust `log` crate are forwarded into Python's logging hierarchy under the name
of the crate that emitted them. One web search emits ~124 of them — HTTP/2
frames, DNS queries and cookie jar writes — so without a level they bury the
agent's own structured output on every turn that uses the tool.

Importing `app.core.logging` runs `setup_logging()` at module scope, which is
what these assert against.
"""

import logging

import pytest

import app.core.logging  # noqa: F401  - imported for its setup_logging() side effect

pytestmark = pytest.mark.unit

# Deliberately leaf names, not the crate roots `setup_logging` configures.
# The silencing relies on level inheritance: only the root is set, and pyo3-log
# creates these children at NOTSET on first use. Asserting the roots would pass
# even if that inheritance stopped holding.
RUST_DEBUG_LOGGERS = [
    "hickory_net.udp.udp_stream",
    "hickory_net.xfer.dns_handle",
    "hickory_resolver.name_server_pool",
    "h2.codec.framed_read",
    "h2.proto.connection",
    "cookie_store.cookie_store",
]


@pytest.mark.parametrize("name", RUST_DEBUG_LOGGERS)
def test_rust_http_tracing_is_silenced(name: str) -> None:
    """Every crate primp routes through must be quiet at DEBUG."""
    assert not logging.getLogger(name).isEnabledFor(logging.DEBUG)


def test_primp_is_silenced_at_info_not_only_debug() -> None:
    """The primp logger emits one request line per call, and at INFO.

    A filter that only reasoned about DEBUG would leave these in production,
    where the floor is INFO.
    """
    assert not logging.getLogger("primp").isEnabledFor(logging.INFO)


def test_silencing_is_scoped_rather_than_a_global_floor() -> None:
    """Non-vacuity: the app's own records must still get through.

    Holds whether or not `settings.DEBUG` is set, since `setup_logging` picks
    DEBUG or INFO and both are below WARNING.
    """
    assert logging.getLogger().getEffectiveLevel() < logging.WARNING


def test_the_ddgs_logger_is_left_audible() -> None:
    """Silencing the Rust crates rests on this logger staying unsilenced.

    hickory reports a DNS failure at DEBUG, which is now dropped — so the
    record that explains a broken search is ddgs's own, one INFO per failed
    engine, carrying the same detail inside the exception it formats:

        Error in engine wikipedia: DDGSException('DNSError: ... > error
        resolving DNS > DNS error: no records found for Query { ... }')

    Adding "ddgs" to `third_party_loggers` would leave a search able to fail
    with nothing said about it anywhere. This is what stops that.
    """
    assert logging.getLogger("ddgs.ddgs").isEnabledFor(logging.INFO)
