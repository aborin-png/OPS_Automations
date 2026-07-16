# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
import json
import pathlib as Path
import sys
import threading
from tkinter import messagebox

import customtkinter as ctk
import glossary
import logger_setup
from afse_monitoring import AfseMonitoringMixin
from API_Post import robot_password
from config_editing import ConfigEditor
from dialogs import (
    AddRobotWindow,
    ConfigUpdateWindow,
    ErrorWindow,
    RemoveRobotWindow,
    SettingsWindow,
    UpdateWindow,
)
from git import InvalidGitRepositoryError, Repo
from logger_setup import log_calls
from robot_detail import RobotDetailWindow
from sheet_editor import SheetEditorMixin
from Sheets_Automation import Sheets_editor, Zone_scanner

# All configuration constants live in glossary.py (single source of truth). These module-level
# aliases keep the references below short and unchanged.
CAMERA_DEFAULT_CHANNEL = glossary.CAMERA_DEFAULT_CHANNEL
CAMERA_CHANNELS = glossary.CAMERA_CHANNELS  # robot Zone ID -> 1-based NVR channel number

ZONE_NAMES = glossary.ZONE_NAMES

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def find_config() -> Path.Path:
    start = Path.Path(sys.executable).parent if getattr(sys, 'frozen',
                                                        False) else Path.Path(__file__).parent
    for directory in [start, *start.parents]:

        candidate = directory / 'Automation_GUI_Config.json'
        if candidate.exists():
            print("Config Found!")
            return candidate
    try:
        repo = Repo(start, search_parent_directories=True)
        path_outside_repo = Path.Path(repo.working_dir).parent / 'Automation_GUI_Config.json'
    except InvalidGitRepositoryError:
        path_outside_repo = start / 'Automation_GUI_Config.json'

    print(
        f'No Automation_GUI_Config.json file detected, creating a default at: {path_outside_repo}')
    with open(path_outside_repo, 'w') as config:
        json.dump(glossary.CONFIG_TEMPLATE, config, indent=4)

    return path_outside_repo


CONFIG_PATH = find_config()

# Set up logging as early as possible (logs live in a folder next to Automation_GUI_Config.json).
logger = logger_setup.setup_logging(CONFIG_PATH.parent / "logs")

# UI appearance / layout constants -- defined in glossary.py, aliased here (see note above).
TAB_COLORS = glossary.TAB_COLORS
STATUS_COLORS = glossary.STATUS_COLORS
CHARGE_STATUS = glossary.CHARGE_STATUS
ROBOT_CARD_COLS = glossary.ROBOT_CARD_COLS
PANEL_COLOR = glossary.PANEL_COLOR
CARD_COLOR = glossary.CARD_COLOR
DIVIDER_COLOR = glossary.DIVIDER_COLOR
SUBTLE_TEXT = glossary.SUBTLE_TEXT


class App(AfseMonitoringMixin, SheetEditorMixin, ctk.CTk):

    def __init__(self):
        super().__init__()

        # Runtime state (not configuration): robots currently unreachable, mutated as robots go
        # on/offline. Shared by the AFSE + Sheet Editor mixins via self.
        self.robot_offline = []

        # Route exceptions raised inside Tk callbacks (button clicks, after() jobs, etc.)
        # into the log instead of just dumping them to the terminal.
        self.report_callback_exception = self._log_callback_exception
        # Surface a crash/error window when an uncaught exception is logged anywhere.
        logger_setup.register_error_handler(self._on_logged_error)

        self.title("OPS Automations")
        self.geometry("900x600")
        self.minsize(700, 450)

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)

        logger.info("Starting OPS Automations GUI")
        self.config = self.load_config()

        # Apply the per-machine UI scaling before any widgets are built. CTk auto-detects DPI,
        # which is unreliable on Linux/HiDPI, so this lets each machine be tuned in Settings.
        self.ui_scaling = float(self.config.get("UI", {}).get("Scaling", 1.0))
        self._apply_ui_scaling(self.ui_scaling)
        self.authentication = Sheets_editor.authenticator()
        self.load_zone_data()

        self.build_main_area()
        self.build_sidebar()

        self.build_afse_monitoring()
        self.build_Sheet_Editor()
        self.build_config_editing()

        self.after(300, lambda: threading.Thread(target=self.update_from_git, daemon=True).start())
        self.after(500, self._check_config_version)

        self.protocol("WM_DELETE_WINDOW", self._on_app_close)

    def _log_callback_exception(self, exc_type, exc_value, exc_tb):
        logger.error("Uncaught exception in Tk callback", exc_info=(exc_type, exc_value, exc_tb))
        self._show_error_window(f"{exc_type.__name__}: {exc_value}")

    def _on_logged_error(self, message):
        """Called (possibly from a worker thread) when an uncaught exception is logged."""
        try:
            self.after(0, lambda: self._show_error_window(message))
        except Exception:
            pass

    def _show_error_window(self, message=None):
        if not self.winfo_exists():
            return
        existing = getattr(self, "_error_win", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus()
            return
        self._error_win = ErrorWindow(self, detail=message)

    @log_calls
    def _on_app_close(self):
        # Cached robot passwords live in memory only; drop them so a reopened GUI re-authorizes.
        logger.info("Shutting down OPS Automations GUI")
        robot_password.clear_password_cache()
        self.destroy()

#----------------------------------------------------------------------------------------------------------------------------------------

#region Baseline Functions

    def build_main_area(self):
        self.tab_view = ctk.CTkTabview(self, corner_radius=8)
        self.tab_view.grid(row=0, column=0, padx=(12, 6), pady=12, sticky="nsew")

        for name in TAB_COLORS:
            self.tab_view.add(name)
            tab = self.tab_view.tab(name)
            ctk.CTkLabel(tab, text=name, font=ctk.CTkFont(size=16, weight="bold")).pack(pady=20)

        for name, color in TAB_COLORS.items():
            btn = self.tab_view._segmented_button._buttons_dict.get(name)
            if btn:
                btn.configure(text_color=color)

    def build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=160, corner_radius=8)
        self.sidebar.grid(row=0, column=1, padx=(6, 12), pady=12, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(0, weight=1)

        ctk.CTkLabel(self.sidebar, text="Menu",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(16, 8), padx=12)

        ctk.CTkFrame(self.sidebar, height=1,
                     fg_color=DIVIDER_COLOR).pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkButton(
            self.sidebar,
            text="Settings",
            command=self.open_settings,
            width=130,
        ).pack(padx=12, pady=4, anchor="n")

#endregion

#----------------------------------------------------------------------------------------------------------------------------------------

# region Auxiliary Functions

    def load_config(self):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)

    def save_config(self):
        """Persist the in-memory config back to Automation_GUI_Config.json."""
        with open(CONFIG_PATH, 'w') as f:
            json.dump(self.config, f, indent=4)

    @log_calls
    def open_settings(self):
        if not hasattr(self, "_settings_win") or not self._settings_win.winfo_exists():
            self._settings_win = SettingsWindow(self)

    def _apply_ui_scaling(self, factor):
        """Override CustomTkinter's (unreliable on Linux) DPI auto-detection."""
        ctk.set_widget_scaling(factor)
        ctk.set_window_scaling(factor)

    @log_calls
    def set_ui_scaling(self, factor):
        """Apply a new UI scaling factor live and persist it to Automation_GUI_Config.json."""
        self.ui_scaling = factor
        self._apply_ui_scaling(factor)
        self.config.setdefault("UI", {})["Scaling"] = factor
        self.save_config()
        logger.info("UI scaling set to %.0f%%", factor * 100)

    @log_calls
    def load_zone_data(self):
        """Scan the STO "global truth" sheet for the current Zone ID -> Dock/Cell mapping and
        overwrite glossary.ZONE_NAMES / glossary.ZONE_TYPES IN PLACE (so every module that imported
        those dicts sees the live data).

        Falls back to the hardcoded glossary values and warns the user if the scan fails.
        """
        try:
            zone_names, zone_types = Zone_scanner.scan_zone_data(self.authentication)
            if not zone_names:
                raise ValueError("No zone data found in the STO sheet.")

            glossary.ZONE_NAMES.clear()
            glossary.ZONE_NAMES.update(zone_names)
            glossary.ZONE_TYPES.clear()
            glossary.ZONE_TYPES.update(zone_types)
            logger.info("Loaded %d zones from the STO sheet.", len(zone_names))
        except Exception as e:
            logger.warning("Zone scan failed, using hardcoded fallback: %s", e)
            self.after(800, lambda err=e: self._notify_zone_fallback(err))

    def _notify_zone_fallback(self, error):
        messagebox.showwarning(
            "Zone data unavailable",
            "Could not load live zone data from the STO sheet, so the GUI is using the "
            "built-in fallback list. Zone names and camera selection may be out of date.\n\n"
            f"Details: {error}",
        )

    '''
        This code is responsible for updating the code base by checking if there is a more recent pull from github.
        This code will find the repo folder that was created when the initial repo was cloned, search if that repo
        has a more recent push to it, and finally pull that change and apply it to the current code base. 
    '''

    @log_calls
    def update_from_git(self):
        start_path = Path.Path(sys.executable).parent if getattr(
            sys, 'frozen', False) else Path.Path(__file__).parent
        try:
            repo = Repo(start_path, search_parent_directories=True)
            origin = repo.remotes.origin
            origin.fetch()

            local_vers = repo.head.commit
            remote_vers = repo.commit('origin/' + repo.active_branch.name)

            if local_vers != remote_vers:
                self.after(
                    0,
                    lambda: UpdateWindow(self, on_update=lambda win: self._start_pull(origin, win)))
        except Exception as e:
            logger.warning("Git update check failed: %s", e)

    @log_calls
    def _start_pull(self, origin, win):
        win.update_btn.configure(state="disabled", text="Updating...")
        win.msg_label.configure(text="Pulling latest changes...")
        threading.Thread(target=self._do_pull, args=(origin, win), daemon=True).start()

    @log_calls
    def _do_pull(self, origin, win):
        try:
            origin.pull()
            self.after(
                0, lambda: win.msg_label.configure(
                    text="Update complete. Please restart the application."))
        except Exception as e:
            self.after(
                0,
                lambda: win.msg_label.configure(text=f"Update failed: {e}", text_color="#CC3333"))

    @log_calls
    def _check_config_version(self):
        current = self.config.get("Version")
        required = glossary.CONFIG_VERSION
        if current != required:
            ConfigUpdateWindow(self, current, required, on_update=self._do_config_update)

    @log_calls
    def _do_config_update(self, win):
        win.keep_btn.grid_remove()
        win.update_btn.grid_remove()
        with open(CONFIG_PATH, 'w') as f:
            json.dump(glossary.CONFIG_TEMPLATE, f, indent=4)
        self.config = self.load_config()
        win.msg_label.configure(text="Config updated. The application will close soon.",
                                text_color="#2E8B3A")

        win.after(1500, win.destroy)
        self.destroy()

#endregion
#----------------------------------------------------------------------------------------------------------------------------------------
############################################################    SHEETS EDITOR    ########################################################
#----------------------------------------------------------------------------------------------------------------------------------------
#region Sheets Editor

    def build_Sheet_Editor(self):
        sheet_tab = self.tab_view.tab("Sheet Editor")
        options = list(self.config.get("Options", {}).keys())

        self.sheet_frame = ctk.CTkFrame(sheet_tab, fg_color=PANEL_COLOR)
        self.sheet_frame.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkLabel(self.sheet_frame, text="Test Type:").grid(row=0, column=0, padx=(12, 8),
                                                               pady=12, sticky="w")

        self.test_type_var = ctk.StringVar(value=options[0] if options else "")

        self._test_type_menu = ctk.CTkOptionMenu(
            self.sheet_frame,
            values=options,
            variable=self.test_type_var,
            command=self.on_test_type_changed,
        )
        self._test_type_menu.grid(row=0, column=1, padx=(0, 12), pady=12, sticky="w")

        self._use_template_var = ctk.BooleanVar(value=False)
        self._template_checkbox = ctk.CTkCheckBox(self.sheet_frame,
                                                  text="Use Template Google Sheet",
                                                  variable=self._use_template_var,
                                                  command=self.on_template_checked)
        self._template_checkbox.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 12),
                                     sticky="w")
        self._template_checkbox.grid_remove()

        self._new_sheet_name_label = ctk.CTkLabel(self.sheet_frame, text="New Sheet Name:")
        self._new_sheet_name_label.grid(row=1, column=2, padx=(8, 4), pady=(0, 12), sticky="w")
        self._new_sheet_name_label.grid_remove()

        self._new_sheet_name_var = ctk.StringVar()
        self._new_sheet_name_entry = ctk.CTkEntry(
            self.sheet_frame,
            textvariable=self._new_sheet_name_var,
            placeholder_text="Enter new sheet name",
            width=180,
        )
        self._new_sheet_name_entry.grid(row=1, column=3, padx=(0, 12), pady=(0, 12), sticky="w")
        self._new_sheet_name_entry.grid_remove()

        ctk.CTkLabel(self.sheet_frame, text="Sheet:").grid(row=2, column=0, padx=(12, 8),
                                                           pady=(0, 12), sticky="w")
        sheet_options = self.get_sheet_options(test_type=self.test_type_var.get())[0]
        self.sheet_selection = sheet_options[0] if sheet_options else ""
        self.test_data = self.selected_option.get('Data', {})
        self.sheet_name = self.selected_option.get('Name', '')
        self._sheet_type_var = ctk.StringVar(value=self.sheet_selection)
        self._sheet_type_menu = ctk.CTkOptionMenu(self.sheet_frame, values=sheet_options,
                                                  variable=self._sheet_type_var,
                                                  command=self.on_sheet_selection)

        self._sheet_type_menu.grid(row=2, column=1, columnspan=2, padx=12, pady=(0, 12), sticky="w")

        ctk.CTkLabel(self.sheet_frame, text="Worksheet:").grid(row=3, column=0, padx=(12, 8),
                                                               pady=(0, 12), sticky="w")
        worksheet_options = self.get_worksheet_options()[0]
        self.worksheet_selection = worksheet_options[0] if worksheet_options else ""
        self.worksheet_template_var = ctk.StringVar(value=self.worksheet_selection)
        self._worksheet_menu = ctk.CTkOptionMenu(self.sheet_frame, values=worksheet_options,
                                                 variable=self.worksheet_template_var,
                                                 command=self.on_worksheet_selection)
        self._worksheet_menu.grid(row=3, column=1, columnspan=2, padx=12, pady=(0, 12), sticky="w")

        ctk.CTkLabel(self.sheet_frame, text="Robot:").grid(row=4, column=0, padx=(12, 8),
                                                           pady=(0, 12), sticky="w")
        self._robot_entry_var = ctk.StringVar()
        self._robot_entry = ctk.CTkEntry(
            self.sheet_frame,
            textvariable=self._robot_entry_var,
            placeholder_text="Enter robot nickname",
            width=180,
        )
        self._robot_entry.grid(row=4, column=1, padx=(0, 8), pady=(0, 12), sticky="w")
        self._robot_entry.bind("<Return>", lambda _: self.check_robot_online())
        self._robot_entry.bind("<FocusOut>", lambda _: self.check_robot_online())

        self._robot_status_label = ctk.CTkLabel(self.sheet_frame, text="")
        self._robot_status_label.grid(row=4, column=2, padx=(0, 12), pady=(0, 12), sticky="w")

        self._generate_btn = ctk.CTkButton(
            self.sheet_frame,
            text="Generate",
            state="disabled",
            command=self.on_generate,
        )
        self._generate_btn.grid(row=5, column=1, padx=(0, 12), pady=(8, 12), sticky="w")

        self._new_sheet_name_var.trace_add("write", lambda *_: self._check_generate_ready())

#endregion
#----------------------------------------------------------------------------------------------------------------------------------------
############################################################    AFSE MONITORING    ######################################################
#----------------------------------------------------------------------------------------------------------------------------------------
#region AFSE Monitoring

    def build_afse_monitoring(self):
        afse_tab = self.tab_view.tab('AFSE Monitoring')
        self._afse_cards = []
        self._robot_detail_windows = {}
        self.afse_instances = []
        self.latest_robot_api = []

        header = ctk.CTkFrame(afse_tab, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkButton(header, text="+ Add Robot", width=120,
                      command=self._open_add_robot).pack(side="right")
        ctk.CTkButton(header, text="− Remove Robot", width=120, fg_color="gray40",
                      command=self._open_remove_robot).pack(side="right", padx=(0, 8))

        self.afse_frame = ctk.CTkScrollableFrame(afse_tab, fg_color=PANEL_COLOR)
        self.afse_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        for col in range(ROBOT_CARD_COLS):
            self.afse_frame.grid_columnconfigure(col, weight=1)

        self._render_afse_cards(self.afse_fetch_data())
        self.afse_schedule_refresh()

    def _render_afse_cards(self, robot_api):
        """(Re)build the AFSE card grid from scratch.

        Used on first build and whenever the monitored robot count changes (e.g. a robot was added).
        """
        for widget in self._afse_cards:
            widget.destroy()
        self._afse_cards = []
        self.afse_instances = []
        self.latest_robot_api = robot_api or []

        if robot_api is None:
            label = ctk.CTkLabel(self.afse_frame, text="Failed to fetch robot data.",
                                 text_color="red")
            label.grid(row=0, column=0, columnspan=ROBOT_CARD_COLS, pady=20)
            self._afse_cards.append(label)
            return

        for i, (name, charge, color_code, charge_code, zone_id) in enumerate(robot_api):
            status_color, status_label = STATUS_COLORS[color_code]
            charge_color, charge_status = CHARGE_STATUS[charge_code]

            card = ctk.CTkFrame(self.afse_frame, fg_color=CARD_COLOR, corner_radius=8)
            card.grid(row=i // ROBOT_CARD_COLS, column=i % ROBOT_CARD_COLS, padx=8, pady=8,
                      sticky="nsew")
            self._afse_cards.append(card)

            ctk.CTkLabel(card, text=name,
                         font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 4), padx=12)

            robot_charge = ctk.CTkLabel(card, text=f"{charge:.0f}%",
                                        font=ctk.CTkFont(size=24, weight="bold"))
            robot_charge.pack(pady=(4, 0))
            ctk.CTkLabel(card, text="Charge", text_color=SUBTLE_TEXT,
                         font=ctk.CTkFont(size=11)).pack(pady=(0, 8))
            robot_charge_status = ctk.CTkLabel(card, text=charge_status, text_color=charge_color,
                                               font=ctk.CTkFont(size=11))
            robot_charge_status.pack(pady=(0, 8))

            status_badge = ctk.CTkFrame(card, fg_color=status_color, corner_radius=6)
            status_badge.pack(pady=(0, 6), padx=12, fill="x")
            robot_status = ctk.CTkLabel(status_badge, text=status_label, text_color="white",
                                        font=ctk.CTkFont(size=12, weight="bold"))
            robot_status.pack(pady=6)

            zone_text = ZONE_NAMES.get(zone_id, 'Not in a Zone')
            robot_zone = ctk.CTkLabel(card, text=zone_text, text_color=SUBTLE_TEXT,
                                      font=ctk.CTkFont(size=12))
            robot_zone.pack(pady=(0, 10))

            self.afse_instances.append(
                [robot_charge, status_badge, robot_status, robot_charge_status, robot_zone])
            self._bind_card_click(card, i)

    @log_calls
    def _open_add_robot(self):
        if getattr(self, "_add_robot_win", None) is not None and self._add_robot_win.winfo_exists():
            self._add_robot_win.focus()
            return
        self._add_robot_win = AddRobotWindow(self, self.config['AFSE']['Robots'],
                                             self._add_robot_to_config)

    @log_calls
    def _open_remove_robot(self):
        if getattr(self, "_remove_robot_win",
                   None) is not None and self._remove_robot_win.winfo_exists():
            self._remove_robot_win.focus()
            return
        self._remove_robot_win = RemoveRobotWindow(self, self.config['AFSE']['Robots'],
                                                   self._remove_robot_from_config)

    def _bind_card_click(self, widget, index):
        handler = lambda _e: self._open_robot_window(index)
        self._bind_recursive(widget, handler)

    def _bind_recursive(self, widget, handler):
        try:
            widget.configure(cursor="hand2")
        except Exception:
            pass
        widget.bind("<Button-1>", handler)
        for child in widget.winfo_children():
            self._bind_recursive(child, handler)

    @log_calls
    def _open_robot_window(self, index):
        if index >= len(self.latest_robot_api):
            return
        name, charge, color_code, charge_code, zone_id = self.latest_robot_api[index]
        existing = self._robot_detail_windows.get(name)
        if existing is not None and existing.winfo_exists():
            existing.focus()
            return
        channel = CAMERA_CHANNELS.get(zone_id, CAMERA_DEFAULT_CHANNEL)
        self._robot_detail_windows[name] = RobotDetailWindow(self, name, charge, color_code,
                                                             charge_code, zone_id=zone_id,
                                                             camera_channel=channel)
#endregion
#----------------------------------------------------------------------------------------------------------------------------------------
############################################################    CONFIG EDITING    ######################################################
#----------------------------------------------------------------------------------------------------------------------------------------
#region Config Editing

    def build_config_editing(self):
        config_tab = self.tab_view.tab("Config Editing")
        self.config_editor = ConfigEditor(config_tab, app=self)
        self.config_editor.pack(fill="both", expand=True, padx=12, pady=(0, 12))


#endregion

#endregion

if __name__ == "__main__":
    app = App()
    app.mainloop()
