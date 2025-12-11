"""
Centralized error handling utilities to reduce boilerplate and improve consistency.

This module provides decorators and context managers for standardized exception handling
across the Local LLHAMA system, reducing code verbosity while preserving proper error logging.
"""

from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Tuple, Type

from .Shared_Logger import LogLevel


class ErrorHandler:
    """Centralized error handling with logging and fallback behaviors."""

    @staticmethod
    def log_error(
        prefix: str,
        error: Exception,
        level: LogLevel = LogLevel.CRITICAL,
        context: str = "",
    ) -> None:
        """
        Standardized error logging format.

        @param prefix Log prefix (e.g., "[MyClass]")
        @param error Exception instance
        @param level LogLevel for the message
        @param context Additional context description
        """
        ctx = f" {context}" if context else ""
        print(f"{prefix} [{level.name}]{ctx}: {type(error).__name__}: {error}")

    @staticmethod
    def handle_with_log(
        prefix: str,
        level: LogLevel = LogLevel.CRITICAL,
        context: str = "",
        reraise: bool = False,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        """
        Decorator for logging exceptions with optional re-raise.

        @param prefix Log prefix for error messages
        @param level LogLevel for error logging
        @param context Additional context description
        @param reraise If True, re-raises exception after logging
        @param exceptions Tuple of exception types to catch

        Usage:
            @ErrorHandler.handle_with_log("[MyClass]", context="processing data")
            def my_function(self):
                # your code
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    ErrorHandler.log_error(prefix, e, level, context)
                    if reraise:
                        raise
                    return None

            return wrapper

        return decorator

    @staticmethod
    def handle_with_fallback(
        prefix: str,
        fallback: Any,
        level: LogLevel = LogLevel.CRITICAL,
        context: str = "",
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        """
        Decorator that returns a fallback value on exception.

        @param prefix Log prefix for error messages
        @param fallback Value to return on exception
        @param level LogLevel for error logging
        @param context Additional context description
        @param exceptions Tuple of exception types to catch

        Usage:
            @ErrorHandler.handle_with_fallback("[MyClass]", fallback=[], context="fetching items")
            def get_items(self):
                # your code
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    ErrorHandler.log_error(prefix, e, level, context)
                    return fallback

            return wrapper

        return decorator

    @staticmethod
    def handle_with_callback(
        prefix: str,
        callback: Callable[[Exception], Any],
        level: LogLevel = LogLevel.CRITICAL,
        context: str = "",
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        """
        Decorator that executes a callback function on exception.

        @param prefix Log prefix for error messages
        @param callback Function to call on exception (receives exception as arg)
        @param level LogLevel for error logging
        @param context Additional context description
        @param exceptions Tuple of exception types to catch

        Usage:
            @ErrorHandler.handle_with_callback(
                "[StateMachine]",
                callback=lambda e: self.transition(State.LISTENING),
                context="processing command"
            )
            def process_command(self):
                # your code
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    ErrorHandler.log_error(prefix, e, level, context)
                    return callback(e)

            return wrapper

        return decorator

    @staticmethod
    @contextmanager
    def catch_and_log(
        prefix: str,
        level: LogLevel = LogLevel.CRITICAL,
        context: str = "",
        suppress: bool = True,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        """
        Context manager for catching and logging exceptions.

        @param prefix Log prefix for error messages
        @param level LogLevel for error logging
        @param context Additional context description
        @param suppress If True, suppresses exception; if False, re-raises
        @param exceptions Tuple of exception types to catch

        Usage:
            with ErrorHandler.catch_and_log("[MyClass]", context="cleanup"):
                # risky operation
        """
        try:
            yield
        except exceptions as e:
            ErrorHandler.log_error(prefix, e, level, context)
            if not suppress:
                raise


class FlaskErrorHandler:
    """Specialized error handlers for Flask routes."""

    @staticmethod
    def handle_route(
        success_status: int = 200,
        error_status: int = 500,
        log_prefix: str = "[Route]",
    ):
        """
        Decorator for Flask routes with standardized JSON responses.

        Automatically wraps successful results in {"success": True, ...} and
        catches exceptions to return {"success": False, "error": "..."}.

        @param success_status HTTP status code for successful responses
        @param error_status HTTP status code for error responses
        @param log_prefix Log prefix for error messages

        Usage:
            @calendar_bp.route("/events", methods=["GET"])
            @login_required
            @FlaskErrorHandler.handle_route()
            def get_events():
                # your code - return dict for success
                return {"events": [...]}
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    from flask import jsonify

                    result = func(*args, **kwargs)
                    # If already a Response object, return as-is
                    if hasattr(result, "status_code"):
                        return result
                    # If tuple (response, status), handle appropriately
                    if isinstance(result, tuple):
                        return result
                    # Wrap dict result
                    return jsonify({"success": True, **result}), success_status
                except Exception as e:
                    from flask import jsonify

                    ErrorHandler.log_error(
                        log_prefix, e, LogLevel.CRITICAL, func.__name__
                    )
                    return jsonify({"success": False, "error": str(e)}), error_status

            return wrapper

        return decorator


class RetryHandler:
    """Handles retry logic with exponential backoff."""

    @staticmethod
    def retry_with_backoff(
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        prefix: str = "[Retry]",
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        """
        Decorator for retrying operations with exponential backoff.

        @param max_retries Maximum number of retry attempts
        @param initial_delay Initial delay between retries (seconds)
        @param backoff_factor Multiplier for delay on each retry
        @param prefix Log prefix for retry messages
        @param exceptions Tuple of exception types that trigger retry

        Usage:
            @RetryHandler.retry_with_backoff(max_retries=3, prefix="[HAClient]")
            def make_request(self):
                # your code
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                import time

                delay = initial_delay
                last_exception = None

                for attempt in range(max_retries):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt < max_retries - 1:
                            print(
                                f"{prefix} [{LogLevel.WARNING.name}] Attempt {attempt + 1}/{max_retries} failed: {e}"
                            )
                            print(
                                f"{prefix} [{LogLevel.INFO.name}] Retrying in {delay:.1f}s..."
                            )
                            time.sleep(delay)
                            delay *= backoff_factor
                        else:
                            ErrorHandler.log_error(
                                prefix,
                                e,
                                LogLevel.CRITICAL,
                                f"All {max_retries} attempts failed",
                            )

                if last_exception:
                    raise last_exception

            return wrapper

        return decorator
