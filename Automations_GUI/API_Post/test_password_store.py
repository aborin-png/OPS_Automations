# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Headless tests for password_store.py.

No pytest in this environment, so this doubles as a runnable script::

    python3 test_password_store.py

Every ``test_*`` function is also pytest-discoverable if pytest is ever added.
"""
import json

import password_store as ps
import pyrage
import pyrage.x25519 as age_x25519


def _fresh_store():
    store = ps.new_store()
    ps.set_password(store, "sb27", "hunter2")
    ps.set_password(store, "sb12", "correct-horse", field="web.bd")
    return store


def test_keypair_shapes():
    secret, recipient = ps.generate_keypair()
    assert secret.startswith("AGE-SECRET-KEY-"), secret[:8]
    assert recipient.startswith("age1"), recipient[:8]


def test_roundtrip_preserves_store():
    secret, recipient = ps.generate_keypair()
    store = _fresh_store()
    blob = ps.encrypt_store(store, recipient)
    out = ps.decrypt_store(blob, secret)
    assert out == store, out


def test_lookup_normalizes_case_and_whitespace():
    store = _fresh_store()
    assert ps.lookup(store, "SB27") == "hunter2"
    assert ps.lookup(store, "  sb27 ") == "hunter2"
    assert ps.lookup(store, "sb99") is None
    assert ps.lookup(store, "sb27", field="nope") is None


def test_wrong_key_raises_wrongkey():
    _, recipient = ps.generate_keypair()
    other_secret, _ = ps.generate_keypair()
    blob = ps.encrypt_store(_fresh_store(), recipient)
    try:
        ps.decrypt_store(blob, other_secret)
    except ps.WrongKeyError:
        return
    raise AssertionError("expected WrongKeyError for a valid but non-matching key")


def test_malformed_key_raises_invalidkey():
    blob = ps.encrypt_store(_fresh_store(), ps.generate_keypair()[1])
    for bad in ["not-a-key", "AGE-SECRET-KEY-totally-bogus", ""]:
        try:
            ps.decrypt_store(blob, bad)
        except ps.InvalidKeyError:
            continue
        except ps.PasswordStoreError:
            # A garbage string that happens to parse but can't decrypt is also acceptable
            # (still a PasswordStoreError the dialog will surface); just must not crash raw.
            continue
        raise AssertionError(f"expected an error for malformed key {bad!r}")


def test_malformed_recipient_raises_invalidkey():
    try:
        ps.encrypt_store(_fresh_store(), "not-a-recipient")
    except ps.InvalidKeyError:
        return
    raise AssertionError("expected InvalidKeyError for a malformed recipient")


def test_valid_age_but_not_a_store_raises_corrupt():
    secret, recipient = ps.generate_keypair()
    rec = age_x25519.Recipient.from_str(recipient)
    # Encrypt something that decrypts fine but isn't our envelope.
    blob = pyrage.encrypt(json.dumps(["just", "a", "list"]).encode(), [rec])
    try:
        ps.decrypt_store(blob, secret)
    except ps.StoreCorruptError:
        return
    raise AssertionError("expected StoreCorruptError for valid-age, non-store plaintext")


def test_decrypt_returns_independent_copy():
    secret, recipient = ps.generate_keypair()
    blob = ps.encrypt_store(_fresh_store(), recipient)
    out = ps.decrypt_store(blob, secret)
    ps.set_password(out, "sb27", "mutated")
    out2 = ps.decrypt_store(blob, secret)
    assert ps.lookup(out2, "sb27") == "hunter2", "decrypt must not share state across calls"


def test_set_remove_list():
    store = ps.new_store()
    ps.set_password(store, "sb27", "p1", field="web.bd")
    ps.set_password(store, "sb27", "p2", field="admin")
    ps.set_password(store, "sb12", "p3")
    assert ps.list_entries(store) == [("sb12", ["web.bd"]), ("sb27", ["admin", "web.bd"])]
    # remove a single field, robot stays
    assert ps.remove_password(store, "sb27", field="admin") is True
    assert ps.lookup(store, "sb27", field="admin") is None
    assert ps.lookup(store, "sb27", field="web.bd") == "p1"
    # remove the last field -> robot entry disappears
    assert ps.remove_password(store, "sb27", field="web.bd") is True
    assert "sb27" not in store["robots"]
    # remove whole robot
    assert ps.remove_password(store, "sb12") is True
    assert store["robots"] == {}
    # removing something absent
    assert ps.remove_password(store, "ghost") is False


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_main())
