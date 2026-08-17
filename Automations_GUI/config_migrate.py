# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Non-destructive config migration.

When the user's Automation_GUI_Config.json is an older CONFIG_VERSION than the template, we used to
overwrite it wholesale -- destroying any custom Sheet Options, the monitored robot list, the RETRO
history, and their saved Settings. Instead we *merge*: the template supplies any keys the user is
missing (new defaults), while the user's existing values win everywhere they already have one.

Two steps, both pure (no widgets / no file I/O -- see UI_Handler._do_config_update for the backup +
save wiring):

  1. ``apply_migrations`` -- explicit fix-ups for structural changes a blind merge can't infer, e.g.
     a key that moved from ``UI.Scaling`` to ``Settings.Scaling``.
  2. ``deep_merge`` -- recursively fill in missing keys from the template; keep the user's value for
     anything already present (dicts recurse; lists/scalars are taken as-is). On a container-shape
     mismatch (dict vs. non-dict) the template's shape wins, so the app never reads a wrong-typed
     value.

``merge_config`` runs both, then stamps the template's Version so the mismatch prompt stops firing.
"""
import copy
import logging
import pathlib

logger = logging.getLogger("OPS.config")


# --------------------------------------------------------------------------------------------------
# Recursive merge
# --------------------------------------------------------------------------------------------------
def deep_merge(template: dict, user: dict) -> dict:
    """Merge ``template`` into ``user`` (user-wins) and return a new dict.

    - keys only in the template are added (new defaults);
    - keys only in the user are kept (their customizations);
    - keys in both: dicts recurse, everything else keeps the user's value;
    - dict-vs-non-dict mismatch: the template's shape wins (logged).
    """
    result = copy.deepcopy(user)
    for key, t_val in template.items():
        if key not in user:
            result[key] = copy.deepcopy(t_val)
            continue
        u_val = user[key]
        if isinstance(t_val, dict) and isinstance(u_val, dict):
            result[key] = deep_merge(t_val, u_val)
        elif isinstance(t_val, dict) != isinstance(u_val, dict):
            logger.warning("Config key %r changed shape; replacing with the new default.", key)
            result[key] = copy.deepcopy(t_val)
        # else: leave the user's value (already present via the deepcopy above)
    return result


# --------------------------------------------------------------------------------------------------
# Explicit migrations (for structural changes deep_merge can't infer)
# --------------------------------------------------------------------------------------------------
def _split(path: str) -> list:
    return path.split(".")


def _get(config: dict, parts: list):
    """(found, value) for a dotted path."""
    cur = config
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def _set(config: dict, parts: list, value) -> None:
    cur = config
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _del(config: dict, parts: list) -> None:
    cur = config
    for part in parts[:-1]:
        if not isinstance(cur, dict) or part not in cur:
            return
        cur = cur[part]
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)


def move(old_path: str, new_path: str):
    """Migration: move a value from ``old_path`` to ``new_path`` (dotted), only if the old path
    exists and the new one isn't already set (so we never clobber a value the user already has)."""

    def _migrate(config: dict) -> None:
        found, value = _get(config, _split(old_path))
        if not found:
            return
        exists, _ = _get(config, _split(new_path))
        if not exists:
            _set(config, _split(new_path), value)
            logger.info("Config migration: moved %r -> %r.", old_path, new_path)
        _del(config, _split(old_path))

    return _migrate


def drop(path: str):
    """Migration: remove a (now-obsolete) dotted path if present."""

    def _migrate(config: dict) -> None:
        found, _ = _get(config, _split(path))
        if found:
            _del(config, _split(path))
            logger.info("Config migration: dropped %r.", path)

    return _migrate


# Ordered list applied before the merge. Add one line per structural change in future releases.
MIGRATIONS = [
    move("UI.Scaling", "Settings.Scaling"),  # scaling moved out of the old "UI" block
    drop("UI"),  # remove the now-empty legacy block
]


def apply_migrations(user: dict) -> dict:
    """Return a copy of ``user`` with every migration in MIGRATIONS applied, in order."""
    config = copy.deepcopy(user)
    for migration in MIGRATIONS:
        migration(config)
    return config


# --------------------------------------------------------------------------------------------------
# Top-level entry points
# --------------------------------------------------------------------------------------------------
def merge_config(template: dict, user: dict) -> dict:
    """Produce the updated config: migrate the user's config, merge template defaults in, then stamp
    the template's Version (which always comes from the template so the mismatch prompt stops).

    ``Options`` is handled at whole-option granularity rather than per-field: each option is a
    self-contained, user-owned unit (they can fully rewrite one -- including switching a field's
    shape -- via the Config Editing tab), so the user's options are kept exactly as-is and the
    template only contributes options the user doesn't already have. Everything else is a normal
    per-field ``deep_merge`` (so, e.g., a new ``Settings`` sub-key is added into the user's block).
    """
    migrated = apply_migrations(user)

    # Merge everything except the user-owned "Options" registry (handled below), so deep_merge never
    # recurses into an individual option and reverts a structural edit.
    template_rest = {k: v for k, v in template.items() if k != "Options"}
    merged = deep_merge(template_rest, migrated)

    template_options = template.get("Options", {})
    user_options = migrated.get("Options", {})
    if isinstance(template_options, dict) and isinstance(user_options, dict):
        # User options win wholesale; template-only defaults are added.
        merged["Options"] = {**copy.deepcopy(template_options), **copy.deepcopy(user_options)}
    elif "Options" in template and "Options" not in merged:
        merged["Options"] = copy.deepcopy(template_options)

    if "Version" in template:
        merged["Version"] = template["Version"]
    return merged


def backup_path(config_path, old_version) -> pathlib.Path:
    """Deterministic sibling path to back the current config up to before an update, tagged with the
    version being replaced, e.g. ``Automation_GUI_Config.backup-1_3_0.json``."""
    path = pathlib.Path(config_path)
    tag = str(old_version or "unknown").replace(".", "_")
    return path.with_name(f"{path.stem}.backup-{tag}{path.suffix}")
