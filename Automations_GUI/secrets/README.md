<!-- Boston Dynamics, Inc. Confidential Information. Copyright 2026. All Rights Reserved. -->

# Robot password store

Encrypted robot passwords for the OPS Automations GUI. Replaces the old approach of
scraping browser cookies to ride a Knox SSO session at runtime.

## What's in this folder

| File                                   | Committed? | What it is                                                                                                                      |
| -------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `robot_passwords.age`                  | **yes**    | The encrypted store. An [age](https://age-encryption.org)-encrypted JSON blob. Safe to commit.                                  |
| `recipient.txt`                        | **yes**    | The **public** age recipient (`age1...`) the store is encrypted to. Safe to commit.                                             |
| the private key (`AGE-SECRET-KEY-...`) | **NEVER**  | The single shared key that decrypts the store. Distributed out-of-band to authorized users; never committed (see `.gitignore`). |

## How it works

- **Operators**: the GUI ships the encrypted `robot_passwords.age` via the existing git
  auto-update. The first time you take an action that needs a robot password, the GUI
  prompts you for the shared key; it stays in memory only (cleared after 1 hour or when the
  GUI closes) and is never written to disk.
- **Maintainers**: edit the store with `manage_password_store.py` (see `--help`). It
  decrypts, applies your change, and re-encrypts to `recipient.txt`. You need the shared
  private key to run any command that reads existing entries.

## Maintainer commands

Run these from the `Automations_GUI` directory. Every command except `keygen` needs the shared
secret key: it's read from `$OPS_ROBOT_PASSWORD_KEY` if set, otherwise you're prompted for it
(never pass it as a CLI argument -- that leaks into shell history and the process table).

```
python Password_Management/manage_password_store.py list                 # nicknames + fields only (never passwords)
python Password_Management/manage_password_store.py set sb27             # add/overwrite sb27's web.bd password (prompted)
python Password_Management/manage_password_store.py set sb27 --field admin
python Password_Management/manage_password_store.py remove sb27 --field admin   # remove one field
python Password_Management/manage_password_store.py remove sb27                 # remove the whole robot
```

## First-time setup

1. `python Password_Management/manage_password_store.py keygen` -- prints a new keypair.
2. Write the printed **recipient** (`age1...`) to `secrets/recipient.txt` and commit it.
3. Store the **secret** (`AGE-SECRET-KEY-...`) somewhere safe; distribute it out-of-band to
   authorized users only. Never commit it.
4. `python Password_Management/manage_password_store.py set <robot>` for each robot, then commit the updated
   `robot_passwords.age`.

## Key rotation / revoking access

Because this is a single shared key (policy: one key handed to all authorized users), removing one
person's access means rotating the key for everyone:

1. `python Password_Management/manage_password_store.py keygen` -- generate a new keypair.
2. Overwrite `secrets/recipient.txt` with the new recipient.
3. Re-add **every** entry under the new key -- the existing store cannot be read with the new key,
   so start fresh: `set <robot>` for each robot (keep the old key handy to `list`/read the old
   store one last time if you need the current values). Commit the new `robot_passwords.age`.
4. Distribute the new secret to the still-authorized users out-of-band and retire the old one.
5. In-flight sessions keep working until their 1-hour cache expires or the GUI restarts, then they
   re-prompt and need the new key.

## Design notes

- Runtime decryption is pure-Python via `pyrage` (no `sops`/`age` binary to install). See the module
  docstrings in `password_store.py` (crypto core) and `manage_password_store.py` (this CLI).
- Nicknames are stored lowercased; lookups normalize case/whitespace.
- The GUI reads the store, and can also _append_ one entry: if an operator takes an action against a
  robot that isn't in the store yet, the GUI prompts for that robot's bd password, verifies it
  against the robot (a non-mutating login), then re-encrypts the store to `recipient.txt` and writes
  it back. This needs only the public recipient, never the shared secret, and only ever writes the
  _encrypted_ file -- decrypted passwords and the key itself are never persisted. That write updates
  the _local_ `robot_passwords.age` only; commit & push it to share the new entry with other machines.
