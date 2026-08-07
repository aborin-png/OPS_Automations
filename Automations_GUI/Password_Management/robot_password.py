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
  * It returns a ``PasswordResult`` so the caller can distinguish a robot that simply isn't in the
    store yet (``"missing"``) from a cancelled unlock. For a ``"missing"`` robot the caller can
    verify a freshly entered password and persist it with ``add_robot_password``, which re-encrypts
    the store to the public recipient and writes the encrypted blob back (the only write path).
  * The cache holds only decrypted data in process memory; it is dropped on GUI shutdown (see
    ``clear_password_cache``). Decrypted passwords are never written to disk -- only the *encrypted*
    store file is ever written.
"""
import logging
import os
import pathlib
import threading
import time
from typing import NamedTuple

from . import password_store  # sibling module in the Password_Management package

logger = logging.getLogger("OPS.robot_password")

STORE_FILENAME = "robot_passwords.age"
RECIPIENT_FILENAME = "recipient.txt"  # public age recipient; needed to WRITE the store (not to read)
STORE_TTL = 60 * 60  # seconds a decrypted store stays cached (matches the old password TTL)


class PasswordResult(NamedTuple):
    """Outcome of resolving a robot's password (see ``get_robot_password``).

    ``status`` is one of:

      * ``"ok"``        -- ``password`` holds the password; ``store`` is the unlocked store.
      * ``"missing"``   -- the store is unlocked (``store`` is set) but has no entry for this robot.
                           The caller may prompt for a password and persist it via
                           ``add_robot_password``.
      * ``"cancelled"`` -- the user dismissed the unlock prompt; ``password`` and ``store`` are None.
    """
    status: str
    password: str | None
    store: dict | None


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


def _recipient_path() -> pathlib.Path:
    """Location of the public age recipient (used only to write/re-encrypt the store)."""
    base = pathlib.Path(__file__).resolve().parent.parent
    return base / "secrets" / RECIPIENT_FILENAME


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


def get_robot_password(robot: str, field: str = "web.bd", unlock=None) -> PasswordResult:
    """Resolve the ``field`` password for ``robot`` from the encrypted store.

    Returns a :class:`PasswordResult` so the caller can tell a genuine *store miss* (the robot has no
    entry yet -- ``"missing"``) apart from the user cancelling the unlock prompt (``"cancelled"``);
    on success the status is ``"ok"`` and ``password`` is set. All non-cancel results also carry the
    unlocked ``store`` dict so the caller can add an entry to it (see ``add_robot_password``).

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
            return PasswordResult("cancelled", None, None)
        _set_cached_store(store)
        logger.info("Robot password store unlocked; cached for %d minutes.", STORE_TTL // 60)

    password = password_store.lookup(store, robot, field)
    if password is None:
        logger.info("No %r password for %s in the store.", field, robot)
        return PasswordResult("missing", None, store)
    logger.info("Resolved the %r password for %s from the store.", field, robot)
    return PasswordResult("ok", password, store)


def _read_recipient() -> str:
    """The public age recipient the store is encrypted to (``secrets/recipient.txt``)."""
    path = _recipient_path()
    if not path.exists():
        raise RuntimeError(f"Cannot save the password: recipient file is missing ({path}).")
    recipient = path.read_text(encoding="utf-8").strip()
    if not recipient:
        raise RuntimeError(f"Cannot save the password: {path} is empty.")
    return recipient


def add_robot_password(store: dict, robot: str, password: str, field: str = "web.bd") -> None:
    """Add ``password`` for ``robot`` to the unlocked ``store``, re-encrypt, write it back, and
    refresh the session cache.

    This is the ONE place the GUI *writes* the store. It re-encrypts to the public recipient
    (``secrets/recipient.txt``) and so never needs the shared secret key -- an operator who has
    unlocked the store this session can persist a newly discovered password. ``store`` must be the
    currently unlocked store dict so existing entries are preserved. The write is atomic (temp file +
    ``os.replace``).

    Note: this updates the *local* ``robot_passwords.age`` only; commit & push it to share the new
    entry with other machines.

    Raises RuntimeError if the recipient file is missing/empty, or password_store.PasswordStoreError
    if encryption fails.
    """
    recipient = _read_recipient()
    password_store.set_password(store, robot, password, field=field)
    blob = password_store.encrypt_store(store, recipient)
    path = _store_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    password_store.save_encrypted(tmp, blob)
    os.replace(tmp, path)
    _set_cached_store(store)  # keep the cache in sync and reset its TTL
    logger.info("Added %s [%s] to the password store; commit robot_passwords.age to share it.",
                robot, field)
