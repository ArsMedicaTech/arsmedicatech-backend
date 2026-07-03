"""
Custom Logger with Colored Output and Sentry integration.
"""

import logging
import sys
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar

import sentry_sdk
from sentry_sdk import push_scope


# ── Error taxonomy ────────────────────────────────────────────────────────────

class ErrorType(Enum):
    api = "api"
    auth = "auth"
    database = "database"
    fhir = "fhir"
    http_request = "http_request"
    media = "media"
    other = "other"


# ── Structured log event ──────────────────────────────────────────────────────

@dataclass
class LogEvent:
    error_type: ErrorType
    component_name: str
    error: BaseException
    stack_trace: Optional[Any] = None
    status_code: Optional[int] = None
    file_name: Optional[str] = None
    line_number: Optional[int] = None
    description: Optional[str] = None
    request_options: Optional[dict] = None
    endpoint: Optional[str] = None
    extra_data: Optional[dict] = None
    level: Optional[str] = None  # "debug" | "info" | "warning" | "error" | "fatal"


# ── Abstract logger ───────────────────────────────────────────────────────────

class AppLogger(ABC):
    @abstractmethod
    def capture(self, error: BaseException, st: Any) -> None:
        """Basic capture — error + traceback."""

    @abstractmethod
    def log(self, event: LogEvent) -> None:
        """Structured event capture."""


# ── Sentry implementation ─────────────────────────────────────────────────────

class SentryLogger(AppLogger):
    """
    Sends structured log events to Sentry / GlitchTip via sentry-sdk.
    Call SentryLogger.init(dsn) once at application startup.
    """

    @staticmethod
    def init(dsn: str, **kwargs: Any) -> None:
        """
        Initialise the Sentry SDK.  Pass any extra sentry_sdk.init kwargs.
        """
        sentry_sdk.init(dsn=dsn, **kwargs)

    def capture(self, error: BaseException, st: Any = None) -> None:
        with push_scope() as scope:
            if st is not None:
                scope.set_extra("traceback", "".join(traceback.format_tb(st)))
            sentry_sdk.capture_exception(error)

    def log(self, event: LogEvent) -> None:
        with push_scope() as scope:
            _LEVEL_MAP = {
                "debug": "debug",
                "info": "info",
                "warning": "warning",
                "error": "error",
                "fatal": "fatal",
            }
            if event.level and event.level.lower() in _LEVEL_MAP:
                scope.level = _LEVEL_MAP[event.level.lower()]

            scope.set_context("error_type", {"value": event.error_type.value})
            scope.set_context("component", {"value": event.component_name})

            if event.status_code is not None:
                scope.set_context("status_code", {"value": event.status_code})
            if event.file_name is not None:
                scope.set_context("file", {"value": event.file_name})
            if event.line_number is not None:
                scope.set_context("line", {"value": event.line_number})
            if event.endpoint is not None:
                scope.set_context("endpoint", {"value": event.endpoint})
            if event.request_options is not None:
                scope.set_context("request_options", event.request_options)
            if event.extra_data is not None:
                scope.set_context("extra", event.extra_data)
            if event.description is not None:
                scope.set_tag("description", event.description)

            sentry_sdk.capture_exception(event.error)


# ── Console implementation ────────────────────────────────────────────────────

class ConsoleLogger(AppLogger):
    """Logs structured events to stdout — useful for local development."""

    def capture(self, error: BaseException, st: Any = None) -> None:
        self.log(LogEvent(
            error_type=ErrorType.other,
            component_name="Uncategorized",
            error=error,
            stack_trace=st,
        ))

    def log(self, event: LogEvent) -> None:
        print("=== Log Event ===")
        print(f"Error Type : {event.error_type.value}")
        print(f"Component  : {event.component_name}")
        if event.level is not None:
            print(f"Level      : {event.level}")
        print(f"Error      : {event.error}")
        if event.stack_trace is not None:
            print(f"Stack Trace:\n{''.join(traceback.format_tb(event.stack_trace))}")
        if event.description is not None:
            print(f"Description: {event.description}")
        if event.status_code is not None:
            print(f"Status Code: {event.status_code}")
        if event.endpoint is not None:
            print(f"Endpoint   : {event.endpoint}")
        print("=================")


# ── guard() helper ────────────────────────────────────────────────────────────

T = TypeVar("T")


def guard(
    action: Callable[[], T],
    *,
    logger: AppLogger,
    error_type: ErrorType = ErrorType.other,
    component: str,
    friendly_msg: str = "Something went wrong. Please try again.",
) -> "Result[T]":
    """
    Wraps a callable, capturing any exception via *logger* and returning a
    typed Result.  Mirrors the Flutter guard() helper.

    Example::

        result = guard(
            lambda: some_service.call(),
            logger=sentry_logger,
            error_type=ErrorType.fhir,
            component="FhirClient.get_patient",
            friendly_msg="Could not retrieve patient record.",
        )
        if result.is_ok:
            data = result.value
        else:
            return jsonify({"error": result.message}), 500
    """
    try:
        return Ok(action())
    except Exception as exc:
        tb = sys.exc_info()[2]
        logger.log(LogEvent(
            error_type=error_type,
            component_name=component,
            error=exc,
            stack_trace=tb,
            description=friendly_msg,
        ))
        return Err(friendly_msg)


# ── Result type ───────────────────────────────────────────────────────────────

class Result(Generic[T]):
    @property
    def is_ok(self) -> bool:
        return isinstance(self, Ok)

    @property
    def is_err(self) -> bool:
        return isinstance(self, Err)


class Ok(Result[T]):
    def __init__(self, value: T) -> None:
        self.value = value


class Err(Result[T]):
    def __init__(self, message: str) -> None:
        self.message = message


# ── Legacy colored-console Logger (kept for backward compatibility) ────────────

class CustomFormatter(logging.Formatter):
    """
    Custom formatter to add colors to log messages based on their severity level.
    """

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    green = "\x1b[32;20m"
    black = "\x1b[30;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    log_format = (
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    )

    FORMATS = {
        # logging.DEBUG: green + log_format + reset,
        logging.DEBUG: black + log_format + reset,
        logging.INFO: grey + log_format + reset,
        logging.WARNING: yellow + log_format + reset,
        logging.ERROR: red + log_format + reset,
        logging.CRITICAL: bold_red + log_format + reset,
    }

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record with the appropriate color based on its level.
        :param record: logging.LogRecord
        :return: str
        """
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class Logger:
    """
    Custom logger class that uses the standard logging library with a custom formatter.
    """

    def __init__(self, name: str = "logger", level: int = logging.WARN) -> None:
        """
        Initialize the logger with a name and logging level.
        :param name: The name of the logger.
        :param level: The logging level (default is logging.WARN).
        :return: None
        """
        logging.basicConfig()
        self._name = name
        self._level = level
        self._logger = logging.getLogger(name)
        # self._logger = logging.getLogger(__name__)
        self._logger = logging.getLogger(name)
        self._logger.propagate = False
        self._handler = logging.StreamHandler()

        self.configure()

    def configure(self) -> None:
        """
        Configure the logger with a custom formatter and set the logging level.
        :return: None
        """
        # formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self._handler.setFormatter(CustomFormatter())
        self._logger.handlers = [self._handler]
        self._logger.setLevel(self._level)
        logging.basicConfig(level=self._level, format="%(message)s")

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log a debug message.
        :param msg: The message to log.
        :param args: Additional arguments to format the message.
        :param kwargs: Additional keyword arguments for logging.
        :return: None
        """
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log an info message.
        :param msg: The message to log.
        :param args: Additional arguments to format the message.
        :param kwargs: Additional keyword arguments for logging.
        :return: None
        """
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log a warning message.
        :param msg: The message to log.
        :param args: Additional arguments to format the message.
        :param kwargs: Additional keyword arguments for logging.
        :return: None
        """
        self._logger.warning(msg, *args, **kwargs)

    def warn(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log a warning message.
        :param msg: The message to log.
        :param args: Additional arguments to format the message.
        :param kwargs: Additional keyword arguments for logging.
        :return: None
        """
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log an error message.
        :param msg: The message to log.
        :param args: Additional arguments to format the message.
        :param kwargs: Additional keyword arguments for logging.
        :return: None
        """
        self._logger.error(msg, *args, **kwargs)
