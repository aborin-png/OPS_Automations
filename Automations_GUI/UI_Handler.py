# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
import json
import logging
import os
import pathlib as Path
import shutil
import sys
import threading
from tkinter import PhotoImage, messagebox

import config_migrate
import customtkinter as ctk
import glossary
import logger_setup
from config_editing import ConfigEditor
from dialogs import (
    AddRobotWindow,
    ConfigUpdateWindow,
    ErrorWindow,
    FavoritesWindow,
    RemoveRobotWindow,
    SettingsWindow,
    UpdateWindow,
)
from git import InvalidGitRepositoryError, Repo
from logger_setup import log_calls
from Password_Management import robot_password
from robot_detail import RobotDetailWindow
from robot_monitoring import RobotMonitoringMixin
from sheet_editor import SheetEditorMixin
from Sheets_Automation import Sheets_editor, Zone_scanner

# All configuration constants live in glossary.py (single source of truth). These module-level
# aliases keep the references below short and unchanged.
CAMERA_DEFAULT_CHANNEL = glossary.CAMERA_DEFAULT_CHANNEL
CAMERA_CHANNELS = glossary.CAMERA_CHANNELS  # robot Zone ID -> 1-based NVR channel number

ZONE_NAMES = glossary.ZONE_NAMES

VERSION_NUMBER_MAJOR = 7
VERSION_NUMBER_MINOR = 1

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def resource_path(*parts) -> Path.Path:
    """Absolute path to a bundled resource, working from source AND from a PyInstaller build.

    PyInstaller unpacks data files bundled via the spec's ``datas`` (or ``--add-data``) into a temp
    dir exposed as ``sys._MEIPASS`` (one-file builds); a plain source run anchors at this file's
    directory instead. Use e.g. ``resource_path("assets", "icon.png")``.
    """
    base = getattr(sys, "_MEIPASS", None)
    base = Path.Path(base) if base else Path.Path(__file__).resolve().parent
    return base.joinpath(*parts)


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


def find_or_seed_secrets(config_dir: Path.Path) -> Path.Path:
    """Ensure a writable ``secrets/`` exists next to the config, seeding it once from the copy baked
    into the app, and point robot_password at it.

    The encrypted store is read-WRITE at runtime (the GUI can add a newly discovered robot's
    password), so it can't live in the read-only PyInstaller bundle, nor inside the git clone (local
    edits would collide with the git auto-update pull). Instead we keep it beside the config file --
    a persistent, user-writable, outside-git location -- and copy the bundled seed
    (robot_passwords.age + recipient.txt) there the first time. Existing files are never
    overwritten, so passwords added locally survive app updates. Mirrors how find_config locates the
    config.
    """
    live = config_dir / "secrets"
    seed = resource_path("secrets")  # baked into the exe (frozen) or the source secrets/ (dev)
    try:
        live.mkdir(parents=True, exist_ok=True)
        for name in (robot_password.STORE_FILENAME, robot_password.RECIPIENT_FILENAME):
            dst, src = live / name, seed / name
            if not dst.exists() and src.exists():
                shutil.copy2(src, dst)
                logger.info("Seeded %s from the bundled copy.", dst)
    except Exception:  # noqa: BLE001 -- seeding must never block startup; store just stays absent
        logger.warning("Could not seed the secrets folder at %s", live, exc_info=True)
    robot_password.set_secrets_dir(live)
    return live


CONFIG_PATH = find_config()

# Set up logging as early as possible (logs live in a folder next to Automation_GUI_Config.json).
logger = logger_setup.setup_logging(CONFIG_PATH.parent / "logs")

# The encrypted robot-password store is writable at runtime, so it lives next to the config (a
# persistent, outside-git spot), seeded once from the copy baked into the app. Must run before any
# robot action can read/write the store. See find_or_seed_secrets / robot_password.set_secrets_dir.
find_or_seed_secrets(CONFIG_PATH.parent)

# UI appearance / layout constants -- defined in glossary.py, aliased here (see note above).
TAB_COLORS = glossary.TAB_COLORS
STATUS_COLORS = glossary.STATUS_COLORS
CHARGE_STATUS = glossary.CHARGE_STATUS
ROBOT_CARD_COLS = glossary.ROBOT_CARD_COLS
PANEL_COLOR = glossary.PANEL_COLOR
CARD_COLOR = glossary.CARD_COLOR
DIVIDER_COLOR = glossary.DIVIDER_COLOR
SUBTLE_TEXT = glossary.SUBTLE_TEXT


class App(RobotMonitoringMixin, SheetEditorMixin, ctk.CTk):

    def __init__(self):
        super().__init__()

        # Runtime state (not configuration): robots currently unreachable, mutated as robots go
        # on/offline. Shared by the Robot Monitoring + Sheet Editor mixins via self.
        self.robot_offline = []

        # Route exceptions raised inside Tk callbacks (button clicks, after() jobs, etc.)
        # into the log instead of just dumping them to the terminal.
        self.report_callback_exception = self._log_callback_exception
        # Surface a crash/error window when an uncaught exception is logged anywhere.
        logger_setup.register_error_handler(self._on_logged_error)

        self.config = self.load_config()
        self.fullscreen = self.config.get("Settings", {}).get("Fullscreen", 0)
        if self.fullscreen:
            self.attributes("-fullscreen", True)
        else:
            self.attributes("-fullscreen", False)
            self.geometry("1000x700")

        # Apply the per-machine UI scaling before any widgets are built. CTk auto-detects DPI,
        # which is unreliable on Linux/HiDPI, so this lets each machine be tuned in Settings.
        self.ui_scaling = float(self.config.get("Settings", {}).get("Scaling", 1.0))
        self._apply_ui_scaling(self.ui_scaling)

        self.title("OPS Automations")

        # Title-bar / taskbar / dock icon shown while the app runs. iconphoto(True, ...) also makes
        # it the default for child dialogs. On Linux the executable itself carries no icon (that's
        # the .desktop launcher's Icon= line); this is what sets the running app's icon. Bundled via
        # the PyInstaller spec's datas and located with resource_path. Kept on self so Tk doesn't
        # garbage-collect the image out from under the window.
        try:
            self._icon_image = PhotoImage(file=str(resource_path("assets", "icon.png")))
            self.iconphoto(True, self._icon_image)
        except Exception:  # noqa: BLE001 -- a missing/unsupported icon must never block startup
            logger.warning("Could not set the window icon", exc_info=True)

        self.minsize(750, 500)

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)

        logger.info("Starting OPS Automations GUI")

        self.authentication = Sheets_editor.authenticator()
        self.load_zone_data()

        self.build_main_area()
        self.build_sidebar()

        self.build_robot_monitoring()
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

#region Base Functions

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

        ctk.CTkButton(self.sidebar, text="Add To Favorites", command=self.favorites_settings,
                      width=130).pack(padx=12, pady=4, anchor="n")

        ctk.CTkLabel(self.sidebar,
                     text=f"Version {VERSION_NUMBER_MAJOR}.{VERSION_NUMBER_MINOR}").pack(
                         padx=12, pady=4, anchor="s")

        ctk.CTkButton(self.sidebar, text="Close",
                      command=self._on_app_close).pack(padx=12, pady=4, anchor="s")

#endregion

#----------------------------------------------------------------------------------------------------------------------------------------

# region Aux. Functions

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

    @log_calls
    def favorites_settings(self):
        if not hasattr(self, "_favorites_win") or not self._favorites_win.winfo_exists():
            self._favorites_win = FavoritesWindow(self)
        else:
            self._favorites_win.focus()

    def _apply_ui_scaling(self, factor):
        """Override CustomTkinter's (unreliable on Linux) DPI auto-detection."""
        ctk.set_widget_scaling(factor)
        ctk.set_window_scaling(factor)

    @log_calls
    def set_ui_scaling(self, factor):
        """Apply a new UI scaling factor live and persist it to Automation_GUI_Config.json."""
        self.ui_scaling = factor
        self._apply_ui_scaling(factor)
        self.config.setdefault("Settings", {})["Scaling"] = factor
        self.save_config()
        logger.info("UI scaling set to %.0f%%", factor * 100)

    def set_fullscreen_setting(self, setting):
        """Apply the new fullscreen setting by changing the size of the GUI to the size of the
        screen and perists to Automation_GUI_Config.json."""
        if setting:
            self.attributes("-fullscreen", True)
        else:
            self.attributes("-fullscreen", False)
            self.geometry("1000x700")

        self.config.setdefault("Settings", {})["Fullscreen"] = setting
        self.save_config()
        logger.info(f"Fullscreen setting set to {setting}")

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
            self.after(0, lambda: self._finish_update(win))
        except Exception as e:
            self.after(
                0, lambda e=e: win.msg_label.configure(text=f"Update failed: {e}", text_color=
                                                       "#CC3333"))

    def _finish_update(self, win):
        """Runs on the main thread after a successful pull: show the success message, then relaunch
        shortly after so the user sees why the window is about to disappear."""
        win.msg_label.configure(text="Update complete. Restarting the application...",
                                text_color="#2E8B3A")
        self.after(1500, self._restart_app)

    @log_calls
    def _restart_app(self):
        """Replace this process with a fresh instance so the freshly pulled code takes effect."""
        logger.info("Restarting OPS Automations GUI to apply update")
        robot_password.clear_password_cache()
        # os.execv does not run atexit handlers, so flush/close the log handlers explicitly.
        logging.shutdown()
        # A frozen build's sys.argv[0] is already the executable; a source run needs the interpreter
        # prepended. os.execv replaces the current process image and never returns.
        args = sys.argv if getattr(sys, 'frozen', False) else [sys.executable, *sys.argv]
        os.execv(sys.executable, args)

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
        old_version = self.config.get("Version")
        try:
            # Back up the current config first so a bad merge is always recoverable.
            backup = config_migrate.backup_path(CONFIG_PATH, old_version)
            shutil.copyfile(CONFIG_PATH, backup)
            # Merge new template defaults in while keeping the user's customizations (user-wins).
            merged = config_migrate.merge_config(glossary.CONFIG_TEMPLATE, self.config)
            with open(CONFIG_PATH, 'w') as f:
                json.dump(merged, f, indent=4)
            self.config = self.load_config()
            logger.info("Config merged %s -> %s (backup: %s).", old_version, merged.get("Version"),
                        backup.name)
        except Exception as e:
            logger.exception("Config merge failed")
            win.msg_label.configure(text=f"Config update failed: {e}", text_color="#CC3333")
            return
        win.msg_label.configure(
            text="Config updated — your customizations were kept. The application will close soon.",
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

        self.build_retro_controls(sheet_tab)

    def build_retro_controls(self, sheet_tab):
        """RETRO section under the Sheet Editor: pick a created worksheet (latest by default, or a
        specific one from history) and fire a retro-log at the robot that worksheet was made for.

        Behaviour lives in SheetEditorMixin (refresh_retro_controls / on_retro_* / open_retro_window).
        """
        # Sequential numbers for blank ("Retro N" / "Comment N") messages this session.
        self._retro_default_count = 0
        self._comment_default_count = 0

        self.retro_frame = ctk.CTkFrame(sheet_tab, fg_color=PANEL_COLOR)
        self.retro_frame.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkLabel(self.retro_frame, text="RETRO", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=4, padx=12, pady=(12, 4), sticky="w")

        ctk.CTkLabel(self.retro_frame, text="Worksheet:").grid(row=1, column=0, padx=(12, 8),
                                                               pady=(0, 8), sticky="w")
        self._retro_source_var = ctk.StringVar(value="Latest")
        ctk.CTkSegmentedButton(self.retro_frame, values=["Latest", "Specific"],
                               variable=self._retro_source_var,
                               command=self.on_retro_source_changed).grid(
                                   row=1, column=1, padx=(0, 8), pady=(0, 8), sticky="w")

        # "Specific" source: type a sheet title, load its tabs, then pick one. The whole sub-frame
        # is shown/hidden together and is only visible in "Specific" mode.
        self._retro_loaded_sheet = None  # cached {key, title, tabs:{title->{id,url}}} after a load
        self._retro_specific_frame = ctk.CTkFrame(self.retro_frame, fg_color="transparent")
        self._retro_specific_frame.grid(row=1, column=2, columnspan=3, padx=(0, 12), pady=(0, 8),
                                        sticky="w")

        self._retro_sheet_entry_label = ctk.CTkLabel(self._retro_specific_frame,
                                                     text="Sheet Title: ",
                                                     font=ctk.CTkFont(size=11),
                                                     text_color=SUBTLE_TEXT)
        self._retro_sheet_entry_label.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self._retro_sheet_var = ctk.StringVar()
        self._retro_sheet_entry = ctk.CTkEntry(self._retro_specific_frame,
                                               textvariable=self._retro_sheet_var,
                                               placeholder_text="Sheet title", width=220)
        self._retro_sheet_entry.grid(row=0, column=1, padx=(0, 8), sticky="w")
        self._retro_sheet_entry.bind("<Return>", lambda _e: self.load_retro_sheet())

        self._retro_load_btn = ctk.CTkButton(self._retro_specific_frame, text="Load Tabs", width=90,
                                             command=self.load_retro_sheet)
        self._retro_load_btn.grid(row=0, column=2, sticky="w")

        self._retro_tab_var = ctk.StringVar(value="(load a sheet)")
        self._retro_tab_menu = ctk.CTkOptionMenu(self._retro_specific_frame, values=[
            "(load a sheet)"
        ], variable=self._retro_tab_var, command=self.on_retro_tab_selected, width=300)
        self._retro_tab_menu.grid(row=1, column=0, columnspan=2, pady=(6, 0), sticky="w")

        self._retro_load_status = ctk.CTkLabel(self._retro_specific_frame, text="",
                                               text_color=SUBTLE_TEXT, font=ctk.CTkFont(size=11))
        self._retro_load_status.grid(row=2, column=0, columnspan=2, pady=(2, 0), sticky="w")

        self._retro_specific_frame.grid_remove()  # only shown in "Specific" mode

        self._retro_target_label = ctk.CTkLabel(self.retro_frame, text="", text_color=SUBTLE_TEXT)
        self._retro_target_label.grid(row=2, column=0, columnspan=4, padx=12, pady=(0, 8),
                                      sticky="w")

        self._retro_btn = ctk.CTkButton(self.retro_frame, text="RETRO", state="disabled",
                                        command=self.open_retro_window)
        self._retro_btn.grid(row=3, column=1, padx=(0, 12), pady=(0, 12), sticky="w")

        self._comment_btn = ctk.CTkButton(self.retro_frame, text="Comment", state="disabled",
                                          fg_color="gray40", command=self.open_comment_window)
        self._comment_btn.grid(row=3, column=2, padx=(0, 12), pady=(0, 12), sticky="w")

        self._image_btn = ctk.CTkButton(self.retro_frame, text="Add Image", state="disabled",
                                        fg_color="gray40", command=self.open_image_window)
        self._image_btn.grid(row=3, column=3, padx=(0, 12), pady=(0, 12), sticky="w")

        self.refresh_retro_controls()

#endregion
#----------------------------------------------------------------------------------------------------------------------------------------
############################################################    ROBOT MONITORING    ######################################################
#----------------------------------------------------------------------------------------------------------------------------------------
#region Robot Monitoring

    def build_robot_monitoring(self):
        robot_tab = self.tab_view.tab('Robot Monitoring')
        self._robot_cards = []
        self._robot_detail_windows = {}
        self.robot_instances = []
        self.latest_robot_api = []

        header = ctk.CTkFrame(robot_tab, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkButton(header, text="+ Add Robot", width=120,
                      command=self._open_add_robot).pack(side="right")
        ctk.CTkButton(header, text="− Remove Robot", width=120, fg_color="gray40",
                      command=self._open_remove_robot).pack(side="right", padx=(0, 8))

        self.robot_frame = ctk.CTkScrollableFrame(robot_tab, fg_color=PANEL_COLOR)
        self.robot_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        for col in range(ROBOT_CARD_COLS):
            self.robot_frame.grid_columnconfigure(col, weight=1)

        self._render_robot_cards(self.fetch_robot_data())
        # Defer the first refresh onto the event loop. schedule_robot_refresh spawns a worker thread
        # that calls self.after() when it finishes; kicking it off directly here (during __init__,
        # before mainloop) lets that thread hit .after() before the loop is running -> "main thread
        # is not in main loop". Scheduling it means the worker only starts once the loop is live.
        self.after(0, self.schedule_robot_refresh)

    def _render_robot_cards(self, robot_api):
        """(Re)build the robot card grid from scratch.

        Used on first build and whenever the monitored robot count changes (e.g. a robot was added).
        """
        for widget in self._robot_cards:
            widget.destroy()
        self._robot_cards = []
        self.robot_instances = []
        self.latest_robot_api = robot_api or []

        if robot_api is None:
            label = ctk.CTkLabel(self.robot_frame, text="Failed to fetch robot data.",
                                 text_color="red")
            label.grid(row=0, column=0, columnspan=ROBOT_CARD_COLS, pady=20)
            self._robot_cards.append(label)
            return

        for i, (name, charge, color_code, charge_code, zone_id) in enumerate(robot_api):
            status_color, status_label = STATUS_COLORS[color_code]
            charge_color, charge_status = CHARGE_STATUS[charge_code]

            card = ctk.CTkFrame(self.robot_frame, fg_color=CARD_COLOR, corner_radius=8)
            card.grid(row=i // ROBOT_CARD_COLS, column=i % ROBOT_CARD_COLS, padx=8, pady=8,
                      sticky="nsew")
            self._robot_cards.append(card)

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

            self.robot_instances.append(
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
