# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Encrypted robot-password store (pure crypto + data core).

Replaces the old "scrape browser cookies to ride a Knox SSO session at runtime" approach. Robot
passwords are kept in a single `age`-encrypted JSON blob (``secrets/robot_passwords.age``) that ships
to operators via the existing git auto-update. It is decrypted **in memory** with a single shared key
the user pastes once per session (see ``robot_password.py`` for the cache + prompt wiring, and
``manage_password_store.py`` for the maintainer editing tool).

This module is deliberately pure: no widgets, no prompts, and the only file I/O is the small
``load_encrypted``/``save_encrypted`` byte helpers. Everything else takes/returns bytes and dicts so it
can be unit-tested headlessly (mirrors the split we use in ``config_migrate.py``).

The decrypted store is a plain dict envelope::

    {"schema": 1, "robots": {"<nickname>": {"<field>": "<password>"}}}

Nicknames are normalized to lowercase (robots are addressed as e.g. ``sb27`` everywhere in the app).
"""
import copy
import json
import logging
import pathlib

import pyrage
import pyrage.x25519 as age_x25519

logger = logging.getLogger("OPS.password_store")

SCHEMA_VERSION = 1
DEFAULT_FIELD = "web.bd"  # the only field any caller requests today; schema allows more


# --------------------------------------------------------------------------------------------------
# Errors -- one base so callers (the unlock dialog) can catch everything with a single except, plus
# specific subclasses so we can show the *right* message (bad key string vs. wrong key vs. corrupt).
# --------------------------------------------------------------------------------------------------
class PasswordStoreError(Exception):
    """Base for every error raised by this module."""


class InvalidKeyError(PasswordStoreError):
    """The provided string isn't a well-formed age key/recipient."""


class WrongKeyError(PasswordStoreError):
    """A valid age key that does not decrypt this particular store."""


class StoreCorruptError(PasswordStoreError):
    """Decryption succeeded but the plaintext isn't a store we understand."""


# --------------------------------------------------------------------------------------------------
# Key generation (used by the maintainer CLI's `keygen`)
# --------------------------------------------------------------------------------------------------
def generate_keypair() -> tuple[str, str]:
    """Return ``(secret_key, recipient)`` for a fresh age identity.

    ``secret_key`` (``AGE-SECRET-KEY-...``) is the shared key distributed out-of-band and pasted into
    the GUI. ``recipient`` (``age1...``) is public and committed to ``secrets/recipient.txt`` so
    maintainers can re-encrypt the store without needing the secret.
    """
    identity = age_x25519.Identity.generate()
    return str(identity), str(identity.to_public())


# --------------------------------------------------------------------------------------------------
# Store data model (pure dict manipulation -- no crypto)
# --------------------------------------------------------------------------------------------------
def new_store() -> dict:
    """An empty, well-formed store envelope."""
    return {"schema": SCHEMA_VERSION, "robots": {}}


def _normalize(nickname: str) -> str:
    return nickname.strip().lower()


def _validate(store) -> dict:
    """Return ``store`` if it's a well-formed envelope, else raise StoreCorruptError."""
    if not isinstance(store, dict) or not isinstance(store.get("robots"), dict):
        raise StoreCorruptError("Decrypted store is not in the expected {schema, robots} shape.")
    return store


def set_password(store: dict, robot: str, password: str, field: str = DEFAULT_FIELD) -> None:
    """Add or overwrite ``field`` for ``robot`` (in place).

    Nickname is normalized to lowercase.
    """
    store.setdefault("robots", {}).setdefault(_normalize(robot), {})[field] = password


def remove_password(store: dict, robot: str, field: str | None = None) -> bool:
    """Remove one ``field`` (or the whole robot when ``field`` is None).

    Returns True if something was removed.
    """
    robots = store.get("robots", {})
    key = _normalize(robot)
    if key not in robots:
        return False
    if field is None:
        del robots[key]
        return True
    removed = robots[key].pop(field, None) is not None
    if not robots[key]:  # drop a now-empty robot entry
        del robots[key]
    return removed


def lookup(store: dict, robot: str, field: str = DEFAULT_FIELD) -> str | None:
    """The password for (robot, field), or None if absent."""
    return store.get("robots", {}).get(_normalize(robot), {}).get(field)


def list_entries(store: dict) -> list[tuple[str, list[str]]]:
    """``[(nickname, [fields...]), ...]`` sorted by nickname -- for the CLI's ``list`` (never prints
    the passwords themselves)."""
    robots = store.get("robots", {})
    return [(name, sorted(robots[name].keys())) for name in sorted(robots)]


# --------------------------------------------------------------------------------------------------
# Crypto: envelope dict <-> encrypted bytes
# --------------------------------------------------------------------------------------------------
def encrypt_store(store: dict, recipient: str) -> bytes:
    """Serialize ``store`` to JSON and age-encrypt it to ``recipient`` (``age1...``)."""
    try:
        rec = age_x25519.Recipient.from_str(recipient.strip())
    except (pyrage.RecipientError, ValueError) as e:
        raise InvalidKeyError(f"Not a valid age recipient: {e}") from e
    plaintext = json.dumps(_validate(store), indent=2).encode("utf-8")
    return pyrage.encrypt(plaintext, [rec])


def decrypt_store(blob: bytes, secret_key: str) -> dict:
    """Age-decrypt ``blob`` with ``secret_key`` and parse it into a store envelope.

    Raises InvalidKeyError (malformed key string), WrongKeyError (valid key, wrong store), or
    StoreCorruptError (decrypted bytes aren't a store we understand).
    """
    try:
        identity = age_x25519.Identity.from_str(secret_key.strip())
    except (pyrage.IdentityError, ValueError) as e:
        raise InvalidKeyError("That doesn't look like a valid age key "
                              "(expected 'AGE-SECRET-KEY-...').") from e
    try:
        plaintext = pyrage.decrypt(blob, [identity])
    except pyrage.DecryptError as e:
        raise WrongKeyError("The key did not unlock the password store. Check that you pasted the "
                            "current shared key.") from e
    try:
        store = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise StoreCorruptError(f"Decrypted store is not valid JSON: {e}") from e
    return copy.deepcopy(_validate(store))


# --------------------------------------------------------------------------------------------------
# Tiny file helpers (the only I/O; kept trivial so the module stays testable)
# --------------------------------------------------------------------------------------------------
def load_encrypted(path) -> bytes:
    return pathlib.Path(path).read_bytes()


def save_encrypted(path, blob: bytes) -> None:
    pathlib.Path(path).write_bytes(blob)