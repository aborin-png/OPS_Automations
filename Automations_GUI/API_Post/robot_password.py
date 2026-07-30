# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Robot password lookup from the encrypted age store.

Previously this read Chrome/Chromium cookies off disk to ride the user's Knox SSO session against the
robot-password service. That is a security violation (the app should not be scraping browser cookies),
so it has been replaced: robot passwords now live in a single ``age``-encrypted blob
(``secrets/robot_passwords.age``, shipped via the existing git auto-update) that is decrypted **in
memory** with a shared key the user pastes once per session.

Flow (see ``password_store.py`` for the pure crypto and ``manage_password_store.py`` for editing):

  * ``get_robot_password`` first checks the in-memory store cache.
  * On a miss it reads the encrypted blob and calls the ``unlock`` callback, which is expected to
    prompt the user for the shared key (on the Tk main thread), decrypt the blob, and return the
    resulting store dict -- or ``None`` if the user cancels. The decrypted store is then cached for
    ``STORE_TTL`` so the user is only prompted once per session.
  * The cache holds only decrypted data in process memory; it is dropped on GUI shutdown (see
    ``clear_password_cache``) and never written to disk, so nothing is persisted.
"""
import logging
import pathlib
import threading
import time

from . import password_store  # sibling module in the API_Post package

logger = logging.getLogger("OPS.robot_password")

STORE_FILENAME = "robot_passwords.age"
STORE_TTL = 60 * 60  # seconds a decrypted store stays cached (matches the old password TTL)


class AuthenticationRequired(RuntimeError):
    """Raised when a password is needed but the store can't be unlocked (missing file / no
    prompt)."""


# In-memory session cache: the decrypted store plus its expiry. Guarded by a lock because
# get_robot_password runs on Sheet Editor / robot-action worker threads. Nothing here touches disk.
_lock = threading.Lock()
_store_cache: dict = {"store": None, "expiry": 0.0}


def _store_path() -> pathlib.Path:
    """Location of the encrypted store: ``secrets/`` next to the Automations_GUI package."""
    base = pathlib.Path(__file__).resolve().parent.parent
    return base / "secrets" / STORE_FILENAME


def clear_password_cache() -> None:
    """Drop the cached decrypted store (called on GUI shutdown / restart)."""
    with _lock:
        _store_cache["store"] = None
        _store_cache["expiry"] = 0.0


def _cached_store():
    with _lock:
        store = _store_cache["store"]
        if store is not None and time.monotonic() < _store_cache["expiry"]:
            return store
        _store_cache["store"] = None
        return None


def _set_cached_store(store) -> None:
    with _lock:
        _store_cache["store"] = store
        _store_cache["expiry"] = time.monotonic() + STORE_TTL


def get_robot_password(robot: str, field: str = "web.bd", unlock=None) -> str | None:
    """Return the ``field`` password for ``robot`` from the encrypted store, or None if the store
    has no entry for it (or the user cancels the unlock prompt).

    ``unlock`` is a callable ``unlock(blob) -> store_dict | None`` supplied by the caller. It is only
    invoked when the store isn't already unlocked this session; it should prompt the user for the
    shared key, decrypt ``blob`` (via ``password_store.decrypt_store``), and return the store dict, or
    ``None`` if the user cancels. On success the decrypted store is cached for ``STORE_TTL``.

    Raises AuthenticationRequired if the store file is missing, or if the store is locked and no
    ``unlock`` callback was provided.
    """
    store = _cached_store()
    if store is None:
        path = _store_path()
        if not path.exists():
            logger.error("Robot password store not found at %s", path)
            raise AuthenticationRequired(f"Robot password store is missing ({path}).")
        blob = password_store.load_encrypted(path)

        if unlock is None:
            raise AuthenticationRequired(
                "Robot passwords are locked and no unlock prompt was given.")

        store = unlock(blob)  # blocks the worker until the user submits/cancels the key dialog
        if store is None:
            logger.info("Robot password unlock cancelled by the user.")
            return None
        _set_cached_store(store)
        logger.info("Robot password store unlocked; cached for %d minutes.", STORE_TTL // 60)

    password = password_store.lookup(store, robot, field)
    if password is None:
        logger.info("No %r password for %s in the store.", field, robot)
    else:
        logger.info("Resolved the %r password for %s from the store.", field, robot)
    return password
