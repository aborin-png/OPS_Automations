#!/usr/bin/env python3
# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Maintainer CLI for the encrypted robot-password store.

The GUI mostly *reads* the store (see Password_Management/robot_password.py); it can also append a
single verified entry on a miss. This tool is the maintainer's full *editor*: it decrypts
``secrets/robot_passwords.age``, applies a change (set/remove/keygen), and re-encrypts
it to the public recipient in ``secrets/recipient.txt``. It's built on the same pure ``password_store``
module the GUI uses, so there's no separate format and no external ``sops``/``age`` binary. Run it from
the Automations_GUI directory (it edits secrets/ at the package root, the same store the GUI reads):

    python3 Password_Management/manage_password_store.py keygen   # new shared keypair (rotation/setup)
    python3 Password_Management/manage_password_store.py list     # nicknames + fields (never passwords)
    python3 Password_Management/manage_password_store.py set sb27  # prompt (hidden) for sb27's web.bd pw
    python3 Password_Management/manage_password_store.py set sb27 --field admin
    python3 Password_Management/manage_password_store.py remove sb27   # drop the whole robot
    python3 Password_Management/manage_password_store.py remove sb27 --field admin

The shared **secret** key (needed by every command that reads existing entries: list/set/remove) is
read from ``$OPS_ROBOT_PASSWORD_KEY`` if set, otherwise prompted for without echo. It is never taken
as a command-line argument (which would leak into shell history / the process table).
"""
import argparse
import getpass
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent  # the Password_Management package dir
PACKAGE_ROOT = HERE.parent  # Automations_GUI (package root)
# password_store is a sibling module in Password_Management; ensure it imports whether this tool is run
# as a script (its own dir is already on sys.path) or imported as Password_Management.manage_password_store.
sys.path.insert(0, str(HERE))

import password_store as ps

# The store + recipient live in secrets/ at the package root -- the SAME folder the GUI reads from
# (see robot_password._store_path), NOT next to this tool under Password_Management/.
SECRETS_DIR = PACKAGE_ROOT / "secrets"
STORE_PATH = SECRETS_DIR / "robot_passwords.age"
RECIPIENT_PATH = SECRETS_DIR / "recipient.txt"
KEY_ENV = "OPS_ROBOT_PASSWORD_KEY"


def _fail(message: str) -> "NoReturn":  # noqa: F821
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def _get_secret_key() -> str:
    key = os.environ.get(KEY_ENV)
    if key:
        return key.strip()
    try:
        return getpass.getpass("Paste the shared decryption key (AGE-SECRET-KEY-...): ").strip()
    except (EOFError, KeyboardInterrupt):
        _fail("no key provided.")


def _get_recipient() -> str:
    if not RECIPIENT_PATH.exists():
        _fail(f"{RECIPIENT_PATH} not found. Run `keygen`, then commit the printed recipient there.")
    recipient = RECIPIENT_PATH.read_text(encoding="utf-8").strip()
    if not recipient:
        _fail(f"{RECIPIENT_PATH} is empty.")
    return recipient


def _load_store_or_empty() -> dict:
    """Decrypt the existing store, or return a fresh empty one if the file doesn't exist yet."""
    if not STORE_PATH.exists():
        print(f"note: {STORE_PATH.name} does not exist yet; starting a new store.", file=sys.stderr)
        return ps.new_store()
    blob = ps.load_encrypted(STORE_PATH)
    try:
        return ps.decrypt_store(blob, _get_secret_key())
    except ps.PasswordStoreError as e:
        _fail(str(e))


def _save_store(store: dict) -> None:
    """Encrypt to the public recipient and write atomically (temp file + replace)."""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    blob = ps.encrypt_store(store, _get_recipient())
    tmp = STORE_PATH.with_suffix(STORE_PATH.suffix + ".tmp")
    ps.save_encrypted(tmp, blob)
    os.replace(tmp, STORE_PATH)


# --------------------------------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------------------------------
def cmd_keygen(_: argparse.Namespace) -> int:
    secret, recipient = ps.generate_keypair()
    print("Generated a new age keypair.\n")
    print("  PUBLIC recipient (safe to commit to secrets/recipient.txt):")
    print(f"    {recipient}\n")
    print("  SECRET key (distribute out-of-band; NEVER commit):")
    print(f"    {secret}\n")
    print("Next: write the recipient to secrets/recipient.txt, then re-run `set` for each robot.")
    print(
        "Rotation note: after changing the key you must re-`set` every entry (the old store cannot")
    print("be read with the new key).")
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    store = _load_store_or_empty()
    entries = ps.list_entries(store)
    if not entries:
        print("(store is empty)")
        return 0
    for nickname, fields in entries:
        print(f"{nickname}: {', '.join(fields)}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    store = _load_store_or_empty()
    try:
        password = getpass.getpass(f"Password for {args.robot} [{args.field}]: ")
    except (EOFError, KeyboardInterrupt):
        _fail("no password provided.")
    if not password:
        _fail("empty password; nothing changed.")
    ps.set_password(store, args.robot, password, field=args.field)
    _save_store(store)
    print(f"set {args.robot} [{args.field}].")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    store = _load_store_or_empty()
    removed = ps.remove_password(store, args.robot, field=args.field)
    if not removed:
        target = f"{args.robot} [{args.field}]" if args.field else args.robot
        _fail(f"{target} not found; nothing changed.")
    _save_store(store)
    what = f"{args.robot} [{args.field}]" if args.field else args.robot
    print(f"removed {what}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("keygen", help="generate a new shared keypair").set_defaults(func=cmd_keygen)
    sub.add_parser("list",
                   help="list nicknames and fields (no passwords)").set_defaults(func=cmd_list)

    p_set = sub.add_parser("set", help="add/overwrite a robot's password (prompts, hidden)")
    p_set.add_argument("robot", help="robot nickname, e.g. sb27")
    p_set.add_argument("--field", default=ps.DEFAULT_FIELD, help=f"default: {ps.DEFAULT_FIELD}")
    p_set.set_defaults(func=cmd_set)

    p_rm = sub.add_parser("remove", help="remove a field, or the whole robot if --field is omitted")
    p_rm.add_argument("robot", help="robot nickname, e.g. sb27")
    p_rm.add_argument("--field", default=None, help="omit to remove the whole robot")
    p_rm.set_defaults(func=cmd_remove)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
