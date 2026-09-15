"""Logging configuration and setup for the application.

This module provides structured logging configuration using structlog,
with environment-specific formatters and handlers. It supports both
console-friendly development logging and JSON-formatted production logging.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    MutableMapping,
)

import structlog
from structlog.types import EventDict

from app.core.config import (
    Environment,
    settings,
)

try:
    from asgi_correlation_id import correlation_id

    CORRELATION_ID_AVAILABLE = True
except ImportError:
    CORRELATION_ID_AVAILABLE = False

# Ensure log directory exists
settings.logging.DIR.mkdir(parents=True, exist_ok=True)

# Cache the project root directory for path relative conversion in logs
_PROJECT_ROOT = Path.cwd()

# Context variables for storing request-specific data
_request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context")


def bind_context(**kwargs: Any) -> None:
    """Bind context variables to the current request."""
    current = _request_context.get({})
    _request_context.set({**current, **kwargs})


def clear_context() -> None:
    """Clear all context variables for the current request."""
    _request_context.set({})


def get_context() -> Dict[str, Any]:
    """Get the current logging context."""
    return _request_context.get({})


def drop_color_message_key(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Drop uvicorn's `color_message` extra, which repeats the message verbatim."""
    event_dict.pop("color_message", None)
    return event_dict


def rename_uvicorn_loggers(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Rename uvicorn logger names to be more descriptive."""
    logger_name = event_dict.get("logger")
    if logger_name == "uvicorn.error":
        event_dict["logger"] = "uvicorn.server"
    elif logger_name == "uvicorn":
        event_dict["logger"] = "uvicorn.main"
    return event_dict


def add_context_to_event_dict(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add the bound context variables, and the correlation ID, to every event."""
    if CORRELATION_ID_AVAILABLE:
        corr_id = correlation_id.get()
        if corr_id:
            event_dict["correlation_id"] = corr_id

    context = get_context()
    if context:
        event_dict.update(context)
    return event_dict


class CustomConsoleRenderer(structlog.dev.ConsoleRenderer):
    """Custom console renderer with colored output for development.

    Adds colors to log levels, logger names, filenames, and other components
    to improve readability during development.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.colors = {
            # Log levels
            "debug": "\033[36m",  # cyan
            "info": "\033[32m",  # green
            "warning": "\033[33m",  # yellow
            "error": "\033[31m",  # red
            "critical": "\033[41m",  # red background
            # Other components
            "logger_name": "\033[1;34m",  # bold blue
            "component": "\033[1;34m",  # bold blue (same as logger_name)
            "message": "\033[39m",  # white
            "filename": "\033[35m",  # magenta
            "func_name": "\033[35m",  # magenta
            "lineno": "\033[35m",  # magenta
            "timestamp": "\033[37m",  # light gray
            "key": "\033[33m",  # yellow for keys
            "value": "\033[97m",  # bright white for values
            "reset": "\033[0m",  # reset color
        }

    def __call__(self, logger: str, name: str, event_dict: MutableMapping[str, Any]) -> str:
        """Render a log event with colors."""
        colored_dict = dict(event_dict)

        # Clean up noisy fields for development console output
        # (Production JSON logs keep everything for aggregation tools)
        colored_dict.pop("http", None)  # Duplicates info in main message
        colored_dict.pop("network", None)  # Duplicates IP:port in main message
        colored_dict.pop("module", None)  # Redundant with filename
        colored_dict.pop("func_name", None)  # Redundant with filename + lineno
        colored_dict.pop("filename", None)  # Not useful in console output

        if "pathname" in colored_dict:
            try:
                pathname_obj = Path(colored_dict["pathname"])
                colored_dict["pathname"] = str(pathname_obj.relative_to(_PROJECT_ROOT))
            except (ValueError, TypeError):
                pass  # not under the project root; keep the absolute path

        if "level" in colored_dict:
            level = colored_dict["level"].lower()
            if level in self.colors:
                colored_dict["level"] = f"{self.colors[level]}{colored_dict['level']}{self.colors['reset']}"

        if "filename" in colored_dict:
            filename = colored_dict["filename"]
            colored_dict["filename"] = f"{self.colors['filename']}{filename}{self.colors['reset']}"

        if "lineno" in colored_dict:
            lineno = colored_dict["lineno"]
            colored_dict["lineno"] = f"{self.colors['lineno']}{lineno}{self.colors['reset']}"

        if "timestamp" in colored_dict:
            timestamp = colored_dict["timestamp"]
            colored_dict["timestamp"] = f"{self.colors['timestamp']}{timestamp}{self.colors['reset']}"

        # Format logger name with component if available
        logger_name = event_dict.get("logger", "")
        component = event_dict.get("component", "")
        event_message = event_dict.get("event", "")

        if event_message and (logger_name or component):
            # Prefer component over logger_name for cleaner output
            # Component is more semantic (e.g., "api-access", "service")
            if component:
                colored_logger = f"{self.colors['component']}[{component}]{self.colors['reset']}"
            else:
                colored_logger = f"{self.colors['logger_name']}[{logger_name}]{self.colors['reset']}"

            colored_message = event_message

            # api-access messages read "IP:PORT - METHOD STATUS \"path\" HTTP/ver".
            # Bold the prefix, colour the status by class.
            if component == "api-access" and "http" in event_dict:
                status_code = event_dict["http"].get("status_code")
                method = event_dict["http"].get("method")

                if method and " - " in colored_message:
                    parts = colored_message.split(f" {status_code} ", 1)
                    if len(parts) == 2:
                        prefix = parts[0]
                        suffix = parts[1]
                        bold = "\033[1m"
                        colored_message = f"{bold}{prefix}{self.colors['reset']} {status_code} {suffix}"

                if status_code:
                    if 200 <= status_code < 300:
                        status_color = "\033[1;32m"  # bold green
                    elif 300 <= status_code < 400:
                        status_color = "\033[1;36m"  # bold light blue
                    elif 400 <= status_code < 500:
                        status_color = "\033[1;33m"  # bold orange/yellow
                    else:  # 500+
                        status_color = "\033[1;31m"  # bold red

                    colored_message = colored_message.replace(
                        f" {status_code} ", f" {status_color}{status_code}{self.colors['reset']} "
                    )

            colored_message = f"{self.colors['message']}{colored_message}{self.colors['reset']}"
            colored_dict["event"] = f"{colored_logger} {colored_message}"

            # Both are now folded into "event"; leave them and they render twice.
            colored_dict.pop("logger", None)
            colored_dict.pop("component", None)

        return super().__call__(logger, name, colored_dict)


def get_log_file_path() -> Path:
    """Get the current log file path based on date and environment."""
    env_prefix = settings.ENVIRONMENT.value
    return settings.logging.DIR / f"{env_prefix}-{datetime.now().strftime('%Y-%m-%d')}.jsonl"


class JsonlFileHandler(logging.Handler):
    """Custom handler for writing JSONL logs to daily files."""

    def __init__(self, file_path: Path):
        """Initialize the JSONL file handler."""
        super().__init__()
        self.file_path = file_path

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a record to the JSONL file."""
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "filename": record.pathname,
                "line": record.lineno,
                "environment": settings.ENVIRONMENT.value,
            }
            if hasattr(record, "extra"):
                log_entry.update(record.extra)

            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """Close the handler."""
        super().close()


def get_structlog_processors(include_file_info: bool = True) -> List[Any]:
    """Get the structlog processors based on configuration."""
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        drop_color_message_key,  # Remove uvicorn's redundant color_message key
        rename_uvicorn_loggers,  # Rename uvicorn loggers to be more descriptive
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        # Add context variables (user_id, conversation_id, etc.) to all log events
        add_context_to_event_dict,
    ]

    if include_file_info:
        processors.append(
            structlog.processors.CallsiteParameterAdder(
                {
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.MODULE,
                    structlog.processors.CallsiteParameter.PATHNAME,
                }
            )
        )

    processors.append(lambda _, __, event_dict: {**event_dict, "environment": settings.ENVIRONMENT.value})

    return processors


def setup_logging() -> None:
    """Configure structlog with different formatters based on environment.

    In development: pretty console output
    In staging/production: structured JSON logs
    """
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # A file handler only outside production, where Docker collects stdout.
    handlers = [console_handler]
    if settings.ENVIRONMENT in [Environment.DEVELOPMENT, Environment.TEST]:
        file_handler = JsonlFileHandler(get_log_file_path())
        file_handler.setLevel(log_level)
        handlers.append(file_handler)

    shared_processors = get_structlog_processors(
        # Callsite info is dev/test only — it costs a stack walk per record.
        include_file_info=settings.ENVIRONMENT in [Environment.DEVELOPMENT, Environment.TEST]
    )

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=handlers,
    )

    # Route uvicorn's own loggers through structlog.
    for logger_name in ["uvicorn", "uvicorn.error", "fastapi"]:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    # Silence uvicorn.access - we handle access logs in AccessLogMiddleware
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False

    # Set third-party library loggers to WARNING level to suppress debug noise
    # This allows our app to log at DEBUG while keeping third-party logs quieter
    third_party_loggers = [
        "multipart",
        "python_multipart",
        "python_multipart.multipart",
        "httpx",
        "httpx._client",
        "httpx._connection",
        "httpx._models",
        "httpcore",
        "httpcore._connection",
        "httpcore._http2",
        # openai>=3 is backed by httpx2, which logs every request at INFO under
        # its own logger name. Without these the OpenAI SDK's traffic lands in
        # the app's structured logs. See langchain_openai._compat.
        "httpx2",
        "httpx2._client",
        "httpcore2",
        # ddgs calls into primp, a Rust extension bridging the `log` crate into
        # Python logging via pyo3-log: one search emits ~124 records, named
        # after the emitting crate and logged at INFO, so production's floor
        # would not stop them. Silencing each crate root is enough — the leaf
        # loggers (hickory_net.udp.udp_stream, h2.codec.framed_read, ...) are
        # created at NOTSET and inherit.
        "primp",
        "h2",
        "hickory_net",
        "hickory_resolver",
        "cookie_store",
        "asyncio",
        "urllib3",
        "urllib3.connectionpool",
        "aiohttp",
        "aiohttp.web",
        "openai._base_client",
        "openai",
    ]
    for logger_name in third_party_loggers:
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.setLevel(logging.WARNING)
        third_party_logger.propagate = True

    if settings.logging.FORMAT == "console":
        structlog.configure(
            processors=[
                *shared_processors,
                CustomConsoleRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )


setup_logging()

logger = structlog.get_logger()
log_level_name = "DEBUG" if settings.DEBUG else "INFO"
logger.info(
    "logging_initialized",
    environment=settings.ENVIRONMENT.value,
    log_level=log_level_name,
    log_format=settings.logging.FORMAT,
    debug=settings.DEBUG,
)
