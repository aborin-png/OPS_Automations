# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""The "Config Editing" tab: add / edit / remove the Sheets-Automation test types in the config.

Each entry under config["Options"] defines a test type the Sheet Editor can generate for (e.g.
Robustness / Endurance / Performance): its Name, its Sheet (a single sheet title, or a
{Template, Folder} pair), its Worksheet (a single name, or a {Cell, Dock} map), and its Data
mapping (sheet column label -> RobotInfo field). This tab lets the user manage those without
hand-editing Automation_GUI_Config.json.

Two modes share one options list:
  * Simple   -- a guided form: pick fields with dropdowns/toggles, optionally cloning an existing
                type as a starting point. This is the default mode.
  * Advanced -- a raw JSON editor for the option body, validated on save.

Self-contained CTk component (constructed by UI_Handler.build_config_editing). The validation /
(de)serialization helpers are module-level pure functions so they can be unit-tested without a
display.
"""
import copy
import dataclasses
import json
import logging
from tkinter import messagebox

import customtkinter as ctk
import glossary
import logger_setup
from glossary import RobotInfo

PANEL_COLOR = glossary.PANEL_COLOR
CARD_COLOR = glossary.CARD_COLOR
SUBTLE_TEXT = glossary.SUBTLE_TEXT
logger = logging.getLogger(logger_setup.LOGGER_NAME)

# Every RobotInfo attribute + derived property is a legal target for a Data mapping value. Derived
# from the dataclass so it stays in sync automatically when RobotInfo changes (see glossary.py).
SHEETABLE_FIELDS = sorted(
    {f.name for f in dataclasses.fields(RobotInfo)} |
    {n for n in dir(RobotInfo) if isinstance(getattr(RobotInfo, n, None), property)})


# --------------------------------------------------------------------------------------------------
# Pure helpers (no widgets) -- unit-testable.
# --------------------------------------------------------------------------------------------------
def default_option(name: str = "New Option") -> dict:
    """A minimal, valid option body used to seed a brand-new entry."""
    return {
        "Name": name,
        "Sheet": "Sheet title here",
        "Worksheet": "Sheet1",
        "Data": {
            "Robot": "nickname",
            "Serial:": "robot_serial",
            "Date:": "date"
        },
    }


def option_to_json(option: dict) -> str:
    return json.dumps(option, indent=4)


def json_to_option(text: str) -> dict:
    """Parse the Advanced-mode text into an option dict, raising ValueError with a readable
    message."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"line {e.lineno}, col {e.colno}: {e.msg}") from e
    if not isinstance(obj, dict):
        raise ValueError("the option must be a JSON object (\"{ ... }\").")
    return obj


def validate_option(name: str, option: dict) -> list[str]:
    """Return a list of human-readable problems with an option; empty means it's valid.

    Mirrors exactly what the Sheet Editor expects (see sheet_editor.py): Sheet is a title string or
    a {Template:{Name,Key}, Folder} object; Worksheet is a name string or a non-empty {label:name}
    object; Data is a non-empty {column-label -> RobotInfo field} map.
    """
    errors: list[str] = []
    if not name or not str(name).strip():
        errors.append("Option name is required.")
    if not isinstance(option, dict):
        return ["The option must be a JSON object."]

    if not option.get("Name") or not str(option.get("Name")).strip():
        errors.append("'Name' field is required.")

    sheet = option.get("Sheet")
    if isinstance(sheet, str):
        if not sheet.strip():
            errors.append("'Sheet' (sheet title) cannot be empty.")
    elif isinstance(sheet, dict):
        template = sheet.get("Template")
        if not isinstance(template, dict) or not template.get("Name") or not template.get("Key"):
            errors.append("A template 'Sheet' needs Template.Name and Template.Key.")
        if not sheet.get("Folder"):
            errors.append("A template 'Sheet' needs a 'Folder' (Google Drive folder ID).")
    else:
        errors.append("'Sheet' must be a sheet title (text) or a {Template, Folder} object.")

    worksheet = option.get("Worksheet")
    if isinstance(worksheet, str):
        if not worksheet.strip():
            errors.append("'Worksheet' cannot be empty.")
    elif isinstance(worksheet, dict):
        if not worksheet:
            errors.append("'Worksheet' object cannot be empty.")
        for key, value in worksheet.items():
            if not isinstance(value, str) or not value.strip():
                errors.append(f"Worksheet '{key}' must map to a non-empty worksheet name.")
    else:
        errors.append("'Worksheet' must be a name (text) or a {Cell, Dock} object.")

    data = option.get("Data")
    if not isinstance(data, dict) or not data:
        errors.append("'Data' must be a non-empty object of column-label -> field.")
    else:
        for label, field in data.items():
            if not isinstance(field, str) or field not in SHEETABLE_FIELDS:
                errors.append(f"Data '{label}' -> '{field}' is not a valid RobotInfo field.")
    return errors


#----------------------------------------------------------------------------------------------------------------------------------------
############################################################    TAB COMPONENTS    ######################################################
#----------------------------------------------------------------------------------------------------------------------------------------
class ConfigEditor(ctk.CTkFrame):
    """Left: the list of options (+ Add / delete). Right: an editor whose form depends on mode.

    `app` is the App instance -- used for config read/write (app.config, app.save_config) and to
    refresh the Sheet Editor's Test Type dropdown (app.refresh_test_types) after a change.
    """

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.mode = "Simple"  # guided form by default; Advanced is the raw-JSON escape hatch
        self.selected = None  # name of the option being edited, or None for a new one
        self._clone_from_name = None  # in Simple mode, which existing option a *new* one clones
        self._build_skeleton()
        self._refresh_list()
        self._render_editor()

    # ---- skeleton ----
    def _build_skeleton(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(top, text="Mode:").pack(side="left", padx=(0, 8))
        self._mode_toggle = ctk.CTkSegmentedButton(top, values=["Simple", "Advanced"],
                                                   command=self._set_mode)
        self._mode_toggle.set(self.mode)
        self._mode_toggle.pack(side="left")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=0, minsize=200)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._list_frame = ctk.CTkScrollableFrame(body, fg_color=PANEL_COLOR, width=200,
                                                  label_text="Sheet Options")
        self._list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self._editor_frame = ctk.CTkFrame(body, fg_color=PANEL_COLOR)
        self._editor_frame.grid(row=0, column=1, sticky="nsew")

    def _set_mode(self, mode):
        self.mode = mode
        self._render_editor()

    # ---- options list ----
    def _refresh_list(self):
        for widget in self._list_frame.winfo_children():
            widget.destroy()
        for name in self.app.config.get("Options", {}):
            row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkButton(row, text=name, anchor="w", fg_color="transparent",
                          hover_color=CARD_COLOR, command=lambda n=name: self._select(n)).pack(
                              side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="✕", width=28, fg_color="gray40",
                          command=lambda n=name: self._delete(n)).pack(side="right", padx=(4, 0))
        ctk.CTkButton(self._list_frame, text="+ Add New",
                      command=self._new).pack(fill="x", pady=(8, 2))

    def _select(self, name):
        self.selected = name
        self._render_editor()

    def _new(self):
        self.selected = None
        self._clone_from_name = None
        self._render_editor()

    # ---- editor dispatch ----
    def _render_editor(self):
        for widget in self._editor_frame.winfo_children():
            widget.destroy()
        if self.mode == "Advanced":
            self._render_advanced()
        else:
            self._render_simple()

    # --------------------------------------------------------------------------------------------------
    # Advanced Mode
    # --------------------------------------------------------------------------------------------------
    def _render_advanced(self):
        name = self.selected
        option = self.app.config.get("Options", {}).get(name) if name else default_option()

        ctk.CTkLabel(self._editor_frame, text=(f"Editing: {name}" if name else "New option"),
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12,
                                                                    pady=(12, 4))

        name_row = ctk.CTkFrame(self._editor_frame, fg_color="transparent")
        name_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(name_row, text="Option name:").pack(side="left", padx=(0, 8))
        self._adv_name_var = ctk.StringVar(value=name or "")
        ctk.CTkEntry(name_row, textvariable=self._adv_name_var, width=240).pack(side="left")

        self._adv_text = ctk.CTkTextbox(self._editor_frame, height=280,
                                        font=ctk.CTkFont(family="Courier", size=12))
        self._adv_text.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self._adv_text.insert("1.0", option_to_json(option))

        self._adv_error = ctk.CTkLabel(self._editor_frame, text="", text_color="#CC3333",
                                       wraplength=520, justify="left")
        self._adv_error.pack(anchor="w", padx=12)

        buttons = ctk.CTkFrame(self._editor_frame, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=(4, 12))
        ctk.CTkButton(buttons, text="Save", command=self._save_advanced).pack(side="left")
        ctk.CTkButton(buttons, text="Cancel", fg_color="gray40",
                      command=self._render_editor).pack(side="left", padx=8)

    def _save_advanced(self):
        name = self._adv_name_var.get().strip()
        try:
            option = json_to_option(self._adv_text.get("1.0", "end"))
        except ValueError as e:
            self._adv_error.configure(text=f"Invalid JSON: {e}")
            return
        errors = validate_option(name, option)
        if errors:
            self._adv_error.configure(text="\n".join("• " + e for e in errors))
            return
        self._commit(name, option, old_name=self.selected)

    # --------------------------------------------------------------------------------------------------
    # Simple Mode
    # --------------------------------------------------------------------------------------------------
    def _render_simple(self):
        """A field-by-field editor.

        Editing seeds from the selected option; a new option seeds from
        the chosen clone source (``_clone_from_name``) or a minimal blank template. Every input owns
        its own widget/var; ``_collect_simple_option`` reads them back into an option dict on Save.
        """
        editing = self.selected is not None
        options = self.app.config.get("Options", {})
        if editing:
            source = copy.deepcopy(options.get(self.selected, default_option("")))
            seed_name = self.selected
        elif self._clone_from_name and self._clone_from_name in options:
            source = copy.deepcopy(options[self._clone_from_name])
            seed_name = ""  # a clone still needs its own name before it can be saved
        else:
            source = default_option("")
            seed_name = ""

        # Save/Cancel bar and error label pinned to the bottom; the form scrolls between them.
        bar = ctk.CTkFrame(self._editor_frame, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=12, pady=(4, 12))
        ctk.CTkButton(bar, text="Save", command=self._save_simple).pack(side="left")
        ctk.CTkButton(bar, text="Cancel", fg_color="gray40",
                      command=self._render_editor).pack(side="left", padx=8)
        self._s_error = ctk.CTkLabel(self._editor_frame, text="", text_color="#CC3333",
                                     wraplength=520, justify="left")
        self._s_error.pack(side="bottom", anchor="w", padx=12)

        form = ctk.CTkScrollableFrame(self._editor_frame, fg_color="transparent")
        form.pack(side="top", fill="both", expand=True, padx=4, pady=4)

        ctk.CTkLabel(form, text=(f"Editing: {self.selected}" if editing else "New option"),
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(4, 4))

        if not editing and options:
            clone_row = ctk.CTkFrame(form, fg_color="transparent")
            clone_row.pack(fill="x", pady=(0, 4))
            ctk.CTkLabel(clone_row, text="Clone From (optional):").pack(side="left", padx=(0, 8))
            clone_var = ctk.StringVar(value=self._clone_from_name or "(blank)")
            ctk.CTkOptionMenu(clone_row, variable=clone_var,
                              values=["(blank)"] + list(options.keys()),
                              command=self._on_clone_change).pack(side="left")

        # --- name ---
        self._section(
            form, "Option name",
            "Shown in the Sheet Editor's Test Type dropdown (also used as the sheet name).")
        self._s_name_var = ctk.StringVar(value=seed_name)
        ctk.CTkEntry(form, textvariable=self._s_name_var, width=300).pack(anchor="w", pady=(0, 4))

        # --- sheet source ---
        sheet = source.get("Sheet")
        sheet_is_template = isinstance(sheet, dict)
        template = sheet.get("Template", {}) if sheet_is_template else {}
        self._s_sheet_mode_var = ctk.StringVar(value="Template" if sheet_is_template else "Single")
        self._s_sheet_title_var = ctk.StringVar(value=sheet if isinstance(sheet, str) else "")
        self._s_tmpl_name_var = ctk.StringVar(value=template.get("Name", ""))
        self._s_tmpl_key_var = ctk.StringVar(value=template.get("Key", ""))
        self._s_folder_var = ctk.StringVar(
            value=sheet.get("Folder", "") if sheet_is_template else "")

        self._section(
            form, "Sheet source",
            "Single: open an existing sheet by title. Template: if multiple sheets are going to be used in a Google Drive folder, type the template sheet name."
        )
        ctk.CTkSegmentedButton(form, values=["Single", "Template"], variable=self._s_sheet_mode_var,
                               command=lambda _v: self._update_sheet_mode()).pack(
                                   anchor="w", pady=(0, 6))
        self._s_sheet_body = ctk.CTkFrame(form, fg_color="transparent")
        self._s_sheet_body.pack(fill="x")

        self._s_sheet_single_frame = ctk.CTkFrame(self._s_sheet_body, fg_color="transparent")
        ctk.CTkLabel(self._s_sheet_single_frame, text="Sheet title:", width=140,
                     anchor="w").pack(side="left", padx=(0, 8))
        ctk.CTkEntry(self._s_sheet_single_frame, textvariable=self._s_sheet_title_var,
                     width=320).pack(side="left")

        self._s_sheet_template_frame = ctk.CTkFrame(self._s_sheet_body, fg_color="transparent")
        for label, var in (("Template name:", self._s_tmpl_name_var),
                           ("Template key (file ID):", self._s_tmpl_key_var), ("Drive folder ID:",
                                                                               self._s_folder_var)):
            row = ctk.CTkFrame(self._s_sheet_template_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=label, width=160, anchor="w").pack(side="left", padx=(0, 8))
            ctk.CTkEntry(row, textvariable=var, width=340).pack(side="left")
        self._update_sheet_mode()

        # --- worksheet ---
        worksheet = source.get("Worksheet")
        ws_is_map = isinstance(worksheet, dict)
        self._s_ws_mode_var = ctk.StringVar(value="Labeled" if ws_is_map else "Single")
        self._s_ws_single_var = ctk.StringVar(value=worksheet if isinstance(worksheet, str) else "")

        self._section(
            form, "Worksheet",
            "Single: one singular worksheet template. Multiple: more than one worksheet template (e.g. Cell / Dock for Robustness)."
        )
        ctk.CTkSegmentedButton(form, values=["Single", "Multiple"], variable=self._s_ws_mode_var,
                               command=lambda _v: self._update_ws_mode()).pack(
                                   anchor="w", pady=(0, 6))
        self._s_ws_body = ctk.CTkFrame(form, fg_color="transparent")
        self._s_ws_body.pack(fill="x")

        self._s_ws_single_frame = ctk.CTkFrame(self._s_ws_body, fg_color="transparent")
        ctk.CTkLabel(self._s_ws_single_frame, text="Worksheet/tab name:", width=140,
                     anchor="w").pack(side="left", padx=(0, 8))
        ctk.CTkEntry(self._s_ws_single_frame, textvariable=self._s_ws_single_var,
                     width=300).pack(side="left")

        self._s_ws_labeled_frame = ctk.CTkFrame(self._s_ws_body, fg_color="transparent")
        self._s_ws_container = ctk.CTkFrame(self._s_ws_labeled_frame, fg_color="transparent")
        self._s_ws_container.pack(fill="x")
        ctk.CTkButton(self._s_ws_labeled_frame, text="+ Add worksheet",
                      command=self._add_ws_row).pack(anchor="w", pady=(4, 0))
        self._s_ws_rows = []
        if ws_is_map:
            for key, value in worksheet.items():
                self._add_ws_row(key, value)
        self._update_ws_mode()

        # --- data ---
        self._section(
            form, "Data (sheet data)",
            "Each row writes to one data member on the sheet: the sheet's data label -> the robot value in SWI."
        )
        self._s_data_container = ctk.CTkFrame(form, fg_color="transparent")
        self._s_data_container.pack(fill="x")
        ctk.CTkButton(form, text="+ Add field",
                      command=self._add_data_row).pack(anchor="w", pady=(4, 8))
        self._s_data_rows = []
        for label, field in source.get("Data", {}).items():
            self._add_data_row(label, field)
        if not self._s_data_rows:
            self._add_data_row()

    def _section(self, parent, title, subtitle=None):
        ctk.CTkLabel(parent, text=title,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(12, 0))
        if subtitle:
            ctk.CTkLabel(parent, text=subtitle, text_color=SUBTLE_TEXT, wraplength=560,
                         justify="left").pack(anchor="w", pady=(0, 4))

    def _on_clone_change(self, choice):
        self._clone_from_name = None if choice == "(blank)" else choice
        self._render_editor()

    def _update_sheet_mode(self):
        if self._s_sheet_mode_var.get() == "Template":
            self._s_sheet_single_frame.pack_forget()
            self._s_sheet_template_frame.pack(fill="x", pady=(0, 4))
        else:
            self._s_sheet_template_frame.pack_forget()
            self._s_sheet_single_frame.pack(fill="x", pady=(0, 4))

    def _update_ws_mode(self):
        if self._s_ws_mode_var.get() == "Labeled":
            self._s_ws_single_frame.pack_forget()
            self._s_ws_labeled_frame.pack(fill="x", pady=(0, 4))
            if not self._s_ws_rows:
                self._add_ws_row()
        else:
            self._s_ws_labeled_frame.pack_forget()
            self._s_ws_single_frame.pack(fill="x", pady=(0, 4))

    def _add_ws_row(self, label="", name=""):
        row = ctk.CTkFrame(self._s_ws_container, fg_color="transparent")
        row.pack(fill="x", pady=2)
        label_var = ctk.StringVar(value=label)
        name_var = ctk.StringVar(value=name)
        ctk.CTkEntry(row, textvariable=label_var, placeholder_text="Label (e.g. Cell)",
                     width=150).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(row, text="→").pack(side="left", padx=(0, 6))
        ctk.CTkEntry(row, textvariable=name_var, placeholder_text="Worksheet/tab name",
                     width=220).pack(side="left")
        entry = (label_var, name_var, row)
        ctk.CTkButton(row, text="✕", width=28, fg_color="gray40",
                      command=lambda: self._remove_row(self._s_ws_rows, entry)).pack(side="right")
        self._s_ws_rows.append(entry)

    def _add_data_row(self, label="", field=None):
        field = field if field in SHEETABLE_FIELDS else SHEETABLE_FIELDS[0]
        row = ctk.CTkFrame(self._s_data_container, fg_color="transparent")
        row.pack(fill="x", pady=2)
        label_var = ctk.StringVar(value=label)
        field_var = ctk.StringVar(value=field)
        ctk.CTkEntry(row, textvariable=label_var, placeholder_text="Column label",
                     width=200).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(row, text="→").pack(side="left", padx=(0, 6))
        ctk.CTkOptionMenu(row, variable=field_var, values=SHEETABLE_FIELDS,
                          width=200).pack(side="left")
        entry = (label_var, field_var, row)
        ctk.CTkButton(row, text="✕", width=28, fg_color="gray40",
                      command=lambda: self._remove_row(self._s_data_rows, entry)).pack(side="right")
        self._s_data_rows.append(entry)

    @staticmethod
    def _remove_row(rows, entry):
        if entry in rows:
            rows.remove(entry)
        entry[-1].destroy()

    def _collect_simple_option(self) -> dict:
        """Assemble an option dict from the Simple-mode widgets (rows with a blank label are
        dropped)."""
        option = {"Name": self._s_name_var.get().strip()}

        if self._s_sheet_mode_var.get() == "Template":
            option["Sheet"] = {
                "Template": {
                    "Name": self._s_tmpl_name_var.get().strip(),
                    "Key": self._s_tmpl_key_var.get().strip()
                },
                "Folder": self._s_folder_var.get().strip(),
            }
        else:
            option["Sheet"] = self._s_sheet_title_var.get().strip()

        if self._s_ws_mode_var.get() == "Labeled":
            option["Worksheet"] = {
                label_var.get().strip(): name_var.get().strip()
                for label_var, name_var, _ in self._s_ws_rows
                if label_var.get().strip()
            }
        else:
            option["Worksheet"] = self._s_ws_single_var.get().strip()

        option["Data"] = {
            label_var.get().strip(): field_var.get()
            for label_var, field_var, _ in self._s_data_rows
            if label_var.get().strip()
        }
        return option

    def _save_simple(self):
        name = self._s_name_var.get().strip()
        option = self._collect_simple_option()
        errors = validate_option(name, option)
        if errors:
            self._s_error.configure(text="\n".join("• " + e for e in errors))
            return
        self._commit(name, option, old_name=self.selected)

    # ---- shared persistence ----
    def _commit(self, name, option, old_name=None):
        options = self.app.config.setdefault("Options", {})
        if old_name and old_name != name and old_name in options:
            del options[old_name]  # a rename: drop the old key
        options[name] = option
        self.app.save_config()
        self.app.refresh_test_types()
        self.selected = name
        self._refresh_list()
        self._render_editor()
        logger.info("Saved sheet option %r", name)

    def _delete(self, name):
        if not messagebox.askyesno("Delete option", f"Delete the '{name}' sheet option?"):
            return
        options = self.app.config.get("Options", {})
        if name in options:
            del options[name]
            self.app.save_config()
            self.app.refresh_test_types()
            logger.info("Deleted sheet option %r", name)
        if self.selected == name:
            self.selected = None
        self._refresh_list()
        self._render_editor()
