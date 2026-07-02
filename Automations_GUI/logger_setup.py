# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Centralized logging for the OPS Automations GUI.

`setup_logging()` does the following, once, at startup:
  - creates a timestamped log file inside a "logs" folder that sits next to Config.json,
  - mirrors everything printed to stdout/stderr (i.e. every existing print() and traceback)
    into that file while still showing it on the console,
  - routes Python warnings and uncaught exceptions (main thread, worker threads, and Tk
    callbacks) into the log,
  - and keeps only the MAX_LOG_FILES newest log files.

Decorate any function with `@log_calls` to record when it is entered and any exception it
raises. Module/feature code can also just do `logging.getLogger("OPS").info(...)`.
"""
#-----------------------------------------------------------------------------------------------------------------------------

import datetime
import functools
import logging
import os
import pathlib
import subprocess
import sys
import threading

#-----------------------------------------------------------------------------------------------------------------------------

LOGGER_NAME = "OPS"
MAX_LOG_FILES = 10
LOG_PREFIX = "OPS_Automations_"

# Captured before stdout/stderr are redirected, so handlers and the tee can reach the real
# terminal without feeding back into themselves.
_original_stdout = sys.stdout
_original_stderr = sys.stderr

# Set by setup_logging(); where the current run's logs live.
_log_dir = None
_log_path = None

# Callbacks invoked when an uncaught exception is logged (used to surface a crash window).
_error_handlers = []


def get_log_dir():
    """Folder the current run's logs are written to (or None before setup_logging)."""
    return _log_dir


def get_log_path():
    """Path of the current run's log file (or None before setup_logging)."""
    return _log_path


def register_error_handler(callback):
    """Register `callback(message)` to be called when an uncaught exception is logged."""
    _error_handlers.append(callback)


def _notify_error(message):
    for callback in list(_error_handlers):
        try:
            callback(message)
        except Exception:
            logging.getLogger(LOGGER_NAME).debug("error handler raised", exc_info=True)


def open_log_folder():
    """Open the folder containing the log files in the system file browser.

    The logs are the primary tool for diagnosing problems, so a failure to open their folder is
    treated as a serious error rather than swallowed: in addition to logging it, we surface it to
    the user through the GUI error window (via the registered error handlers) together with the
    underlying exception, so the user is warned and given something actionable to report.
    """
    if _log_dir is None:
        message = ("Could not open the log folder: logging is not initialized (no log directory "
                   "is set). The application may not be operating safely.")
        logging.getLogger(LOGGER_NAME).error(message)
        _notify_error(message)
        return
    path = str(_log_dir)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        logging.getLogger(LOGGER_NAME).exception("Failed to open log folder %s", path)
        _notify_error(f"Failed to open the log folder ({path}): {type(e).__name__}: {e}")


class _StreamTee:
    """File-like object that writes to the real stream AND mirrors whole lines to a logger."""

    def __init__(self, original, logger, level):
        self._original = original
        self._logger = logger
        self._level = level
        self._buffer = ""

    def write(self, message):
        self._original.write(message)
        self._buffer += message
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self._logger.log(self._level, line)
        return len(message)

    def flush(self):
        self._original.flush()

    def isatty(self):
        return getattr(self._original, "isatty", lambda: False)()


def log_calls(func):
    """Decorator that logs entry into `func` and any exception it raises.

    Arguments are deliberately NOT logged, to avoid leaking sensitive values (e.g. robot passwords).
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(f"{LOGGER_NAME}.calls")
        logger.debug("CALL %s()", func.__qualname__)
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.exception("EXCEPTION in %s()", func.__qualname__)
            raise

    return wrapper


def _prune_old_logs(log_dir, keep=MAX_LOG_FILES):
    """Delete all but the `keep` most recent log files in `log_dir`."""
    logs = sorted(log_dir.glob(f"{LOG_PREFIX}*.log"), key=lambda p: p.stat().st_mtime)
    for old in logs[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass


def _install_exception_hooks(logger):
    """Funnel uncaught exceptions from the main thread and worker threads into the log."""
    original_excepthook = sys.excepthook

    def handle(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            original_excepthook(exc_type, exc, tb)
            return
        logger.error("Uncaught exception", exc_info=(exc_type, exc, tb))
        _notify_error(f"{exc_type.__name__}: {exc}")

    sys.excepthook = handle

    def thread_handle(args):
        if issubclass(args.exc_type, SystemExit):
            return
        logger.error(
            "Uncaught exception in thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        _notify_error(f"{args.exc_type.__name__}: {args.exc_value}")

    threading.excepthook = thread_handle


def setup_logging(log_dir):
    """Configure logging for the whole process and return the main "OPS" logger.

    `log_dir` is the folder to write logs into (created if missing) — typically the folder
    that contains Config.json.
    """
    global _log_dir, _log_path

    log_dir = pathlib.Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = log_dir / f"{LOG_PREFIX}{timestamp}.log"
    _log_dir = log_dir
    _log_path = log_path

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    console_handler = logging.StreamHandler(_original_stdout)
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Quiet down chatty third-party libraries so the log stays useful.
    for noisy in ("PIL", "urllib3", "requests", "comtypes", "git", "googleapiclient", "gspread"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.captureWarnings(True)

    # Mirror stdout/stderr into the file. The console already shows them via the real
    # stream, so this dedicated logger is file-only (propagate=False) to avoid duplicates.
    stream_logger = logging.getLogger(f"{LOGGER_NAME}.stdout")
    stream_logger.propagate = False
    stream_logger.setLevel(logging.DEBUG)
    stream_logger.addHandler(file_handler)
    sys.stdout = _StreamTee(_original_stdout, stream_logger, logging.INFO)
    sys.stderr = _StreamTee(_original_stderr, stream_logger, logging.ERROR)

    logger = logging.getLogger(LOGGER_NAME)
    _install_exception_hooks(logger)

    _prune_old_logs(log_dir)

    logger.info("===== Logging started -> %s =====", log_path)
    return logger
