# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""CustomTkinter dialog / popup windows used by the Automations GUI.

These are the self-contained ``CTkToplevel`` dialogs the main App opens. Each takes its parent App
(and any callbacks) as arguments and does not reach into App internals, so they live here separately
from UI_Handler.py. See UI_Handler.py for the App that instantiates them.
"""
import threading

import customtkinter as ctk
import glossary
import logger_setup
from Sheets_Automation import API_fetch

# UI color alias (defined in glossary.py, single source of truth). See UI_Handler.py.
SUBTLE_TEXT = glossary.SUBTLE_TEXT


class SettingsWindow(ctk.CTkToplevel):
    """Settings dialog for per-machine UI preferences.

    Lets the user choose a UI scaling factor (applied live and persisted to
    Automation_GUI_Config.json, to work around CustomTkinter's unreliable DPI auto-detection on
    Linux) and toggle between Light and Dark appearance modes.
    """
    SCALING_OPTIONS = ["80%", "90%", "100%", "110%", "125%", "150%", "175%", "200%"]

    def __init__(self, parent):
        super().__init__(parent)
        self._app = parent
        self.title("Settings")
        self.geometry("400x300")
        self.resizable(False, False)

        ctk.CTkLabel(self, text="Settings", font=ctk.CTkFont(size=20,
                                                             weight="bold")).pack(pady=(20, 12))

        ctk.CTkLabel(self, text="UI Scaling", text_color=SUBTLE_TEXT).pack(pady=(4, 2))
        current = f"{int(round(self._app.ui_scaling * 100))}%"
        self._scaling_var = ctk.StringVar(value=current)
        ctk.CTkOptionMenu(
            self,
            values=self.SCALING_OPTIONS,
            variable=self._scaling_var,
            command=self._on_scaling_change,
            width=160,
        ).pack(pady=(0, 4))
        ctk.CTkLabel(
            self,
            text="Adjusts text and widget size for this machine.\nApplies immediately and is saved.",
            text_color=SUBTLE_TEXT,
            font=ctk.CTkFont(size=11),
            justify="center",
        ).pack(pady=(0, 10))

        ctk.CTkLabel(self, text="Appearance Mode", text_color=SUBTLE_TEXT).pack(pady=(4, 2))
        self._appearance_var = ctk.StringVar(value=ctk.get_appearance_mode())
        ctk.CTkOptionMenu(
            self,
            values=["Light", "Dark"],
            variable=self._appearance_var,
            command=self._appearance_mode_changed,
            width=160,
        ).pack(pady=(0, 4))

        ctk.CTkButton(self, text="Close", command=self.destroy).pack(pady=(8, 20))

        self.wait_visibility()
        self.grab_set()

    def _on_scaling_change(self, choice):
        factor = int(choice.rstrip('%')) / 100.0
        self._app.set_ui_scaling(factor)

    def _appearance_mode_changed(self, choice):
        ctk.set_appearance_mode(choice)


class UpdateWindow(ctk.CTkToplevel):
    """Prompt shown when a newer version of the app exists on the git remote.

    Offers to pull the latest changes (handing the work off to the `on_update` callback) or to
    cancel and keep running the current version.
    """

    def __init__(self, parent, on_update):
        super().__init__(parent)
        self.title("OPS Automations Update")
        self.geometry("420x220")
        self.resizable(False, False)

        ctk.CTkLabel(self, text="Update Available",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        self.msg_label = ctk.CTkLabel(self, text="Would you like to update to the latest version?",
                                      text_color=SUBTLE_TEXT)
        self.msg_label.pack(pady=10)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)
        self.update_btn = ctk.CTkButton(btn_frame, text="Update", command=lambda: on_update(self))
        self.update_btn.pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="Cancel", command=self.destroy,
                      fg_color="gray40").pack(side="left", padx=8)

        self.wait_visibility()
        self.grab_set()


class ProgressWindow(ctk.CTkToplevel):
    """Modal progress dialog shown while a Google Sheet is being generated.

    Exposes `set_progress(value, message)` so the background worker can drive the progress bar and
    status text as it moves through the fetch / duplicate / write steps.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Generating Sheet")
        self.geometry("420x150")
        self.resizable(False, False)

        ctk.CTkLabel(self, text="Generating Sheet...",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 10))

        self._progress_bar = ctk.CTkProgressBar(self, width=380)
        self._progress_bar.set(0)
        self._progress_bar.pack(pady=(0, 8), padx=20)

        self._status_label = ctk.CTkLabel(self, text="Starting...", text_color=SUBTLE_TEXT)
        self._status_label.pack(pady=(0, 16))

        self.wait_visibility()
        self.grab_set()

    def set_progress(self, value: float, message: str):
        self._progress_bar.set(value)
        self._status_label.configure(text=message)


class ConfigUpdateWindow(ctk.CTkToplevel):
    """Prompt shown when the user's Automation_GUI_Config.json version does not match the required
    CONFIG_VERSION.

    Warns that updating overwrites their Automation_GUI_Config.json (losing any custom edits) and offers to
    regenerate it from the template (`on_update`) or keep the current one.
    """

    def __init__(self, parent, current_version, required_version, on_update):
        super().__init__(parent)
        self.title("Config Version Mismatch")
        self.geometry("460x280")
        self.resizable(False, False)

        ctk.CTkLabel(self, text="Config Version Mismatch",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 4))

        ver_current = current_version if current_version is not None else "not found"
        ctk.CTkLabel(self,
                     text=f"Your version: {ver_current}     Required version: {required_version}",
                     text_color=SUBTLE_TEXT).pack(pady=(0, 12))

        warning_frame = ctk.CTkFrame(self, fg_color="#3d2000", corner_radius=6)
        warning_frame.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(
            warning_frame,
            text=
            "⚠  Updating will overwrite your Automation_GUI_Config.json.\nBack up any custom changes before continuing.",
            text_color="#ffcc44",
            justify="center",
        ).pack(pady=10, padx=12)

        self.msg_label = ctk.CTkLabel(self, text="")
        self.msg_label.pack(pady=(0, 6))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 16))
        self.update_btn = ctk.CTkButton(btn_frame, text="Update Config",
                                        command=lambda: on_update(self))
        self.update_btn.pack(side="left", padx=8)
        self.keep_btn = ctk.CTkButton(btn_frame, text="Keep Current", command=self.destroy,
                                      fg_color="gray40")
        self.keep_btn.pack(side="left", padx=8)

        self.wait_visibility()
        self.grab_set()


class ErrorWindow(ctk.CTkToplevel):
    """Shown when an unexpected error / crash occurs.

    Tells the user something went wrong, offers a button to open the folder where logs are stored,
    and reminds them to attach those logs to any bug report.
    """

    def __init__(self, parent, detail=None):
        super().__init__(parent)
        self.title("Application Error")
        self.geometry("540x320")
        self.resizable(False, False)
        self.transient(parent)

        ctk.CTkLabel(
            self,
            text="⚠  An error has occurred",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#ffcc44",
        ).pack(pady=(20, 6))
        ctk.CTkLabel(
            self,
            text=
            "The application ran into a problem and may not behave correctly.\nThe details have been recorded in the log files.",
            text_color=SUBTLE_TEXT,
            justify="center",
        ).pack(pady=(0, 8))

        if detail:
            box = ctk.CTkFrame(self, fg_color="#3d2000", corner_radius=6)
            box.pack(fill="x", padx=20, pady=(0, 8))
            ctk.CTkLabel(box, text=str(detail), text_color="#ffcc44", wraplength=470,
                         justify="left").pack(pady=8, padx=12)

        ctk.CTkLabel(
            self,
            text=
            "If you are submitting a bug report, please include the relevant\nlog files from the folder below with your report.",
            text_color=SUBTLE_TEXT,
            justify="center",
        ).pack(pady=(4, 12))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=(0, 16))
        ctk.CTkButton(btns, text="Open Logs Folder", width=160,
                      command=logger_setup.open_log_folder).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Close", width=120, fg_color="gray40",
                      command=self.destroy).pack(side="left", padx=6)

        self.wait_visibility()
        self.lift()
        self.focus()


class AuthWaitWindow(ctk.CTkToplevel):
    """Small status window shown only when robot-password retrieval needs the user to authorize in
    their browser.

    Starts on a "waiting for authorization" spinner and is flipped to a green checkmark once the
    password is retrieved and the command is sent.
    """

    def __init__(self, parent, robot_name, action_name):
        super().__init__(parent)
        self.title("Authorization Required")
        self.geometry("440x240")
        self.resizable(False, False)
        self.transient(parent)

        ctk.CTkLabel(self, text=f"{action_name} — {robot_name}",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 8))

        self._icon = ctk.CTkLabel(self, text="⏳", font=ctk.CTkFont(size=40))
        self._icon.pack(pady=(4, 8))

        self._msg = ctk.CTkLabel(
            self,
            text="A browser window was opened.\nPlease click AUTHORIZE to continue.",
            text_color=SUBTLE_TEXT,
            justify="center",
        )
        self._msg.pack(pady=(0, 12))

        self._bar = ctk.CTkProgressBar(self, width=320, mode="indeterminate")
        self._bar.pack(pady=(0, 16), padx=20)
        self._bar.start()

        self._close_btn = ctk.CTkButton(self, text="Close", command=self.destroy, fg_color="gray40")

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def show_success(self, message):
        if not self.winfo_exists():
            return
        self._bar.stop()
        self._bar.pack_forget()
        self._icon.configure(text="✓", text_color="#2E8B3A")
        self._msg.configure(text=message, text_color="#2E8B3A")
        self._close_btn.pack(pady=(0, 16))
        self.after(4000, self._safe_destroy)

    def show_failure(self, message):
        if not self.winfo_exists():
            return
        self._bar.stop()
        self._bar.pack_forget()
        self._icon.configure(text="✕", text_color="#CC3333")
        self._msg.configure(text=message, text_color="#CC3333")
        self._close_btn.pack(pady=(0, 16))

    def _safe_destroy(self):
        if self.winfo_exists():
            self.destroy()


class AddRobotWindow(ctk.CTkToplevel):
    """Dialog for adding a robot to the AFSE monitoring list.

    Validates the name isn't a
    duplicate, confirms the robot is reachable, then hands the name off to `on_added`
    (which persists it to the config and refreshes the tab).
    """

    def __init__(self, parent, existing_robots, on_added):
        super().__init__(parent)
        self.title("Add Robot")
        self.geometry("400x240")
        self.resizable(False, False)
        self.transient(parent)
        self._existing = {r.lower() for r in existing_robots}
        self._on_added = on_added

        ctk.CTkLabel(self, text="Add Robot to Monitor",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 8))
        ctk.CTkLabel(self, text="Enter the robot's name (e.g. sb20):",
                     text_color=SUBTLE_TEXT).pack(pady=(0, 6))

        self._entry = ctk.CTkEntry(self, width=240)
        self._entry.pack(pady=(0, 8))
        self._entry.bind("<Return>", lambda _e: self._submit())

        self._status = ctk.CTkLabel(self, text="", text_color=SUBTLE_TEXT)
        self._status.pack(pady=(0, 8))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=(0, 12))
        self._add_btn = ctk.CTkButton(btns, text="Add", width=100, command=self._submit)
        self._add_btn.pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Cancel", width=100, fg_color="gray40",
                      command=self.destroy).pack(side="left", padx=6)

        self.wait_visibility()
        self.grab_set()
        self._entry.focus()

    def _set_status(self, text, color="gray70"):
        self._status.configure(text=text, text_color=color)

    def _submit(self):
        name = self._entry.get().strip()
        if not name:
            self._set_status("Please enter a robot name.", "#CC3333")
            return
        if name.lower() in self._existing:
            self._set_status(f"'{name}' is already being monitored.", "#CC3333")
            return
        self._add_btn.configure(state="disabled")
        self._set_status(f"Checking if {name} is reachable...")
        threading.Thread(target=self._check, args=(name,), daemon=True).start()

    def _check(self, name):
        reachable = API_fetch.API_Fetch(name, []) is not None
        self.after(0, lambda: self._finish(name, reachable))

    def _finish(self, name, reachable):
        if not self.winfo_exists():
            return
        if not reachable:
            self._add_btn.configure(state="normal")
            self._set_status(f"{name} is not reachable. Check the name and that it's powered on.",
                             "#CC3333")
            return
        try:
            self._on_added(name)
        except Exception as e:
            self._add_btn.configure(state="normal")
            self._set_status(f"Failed to save: {e}", "#CC3333")
            return
        self._set_status(f"{name} added!", "#2E8B3A")
        self.after(1200, self._safe_destroy)

    def _safe_destroy(self):
        if self.winfo_exists():
            self.destroy()


class RemoveRobotWindow(ctk.CTkToplevel):
    """Dialog for removing a robot from the AFSE monitoring list.

    Presents a dropdown of the
    currently monitored robots and hands the chosen name to `on_removed` (which strips it
    from the config and refreshes the tab).
    """

    def __init__(self, parent, monitored_robots, on_removed):
        super().__init__(parent)
        self.title("Remove Robot")
        self.geometry("400x230")
        self.resizable(False, False)
        self.transient(parent)
        self._on_removed = on_removed

        ctk.CTkLabel(self, text="Remove Monitored Robot",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 8))

        if monitored_robots:
            ctk.CTkLabel(self, text="Select a robot to remove:",
                         text_color=SUBTLE_TEXT).pack(pady=(0, 6))
            self._selection = ctk.StringVar(value=monitored_robots[0])
            self._menu = ctk.CTkOptionMenu(self, values=list(monitored_robots),
                                           variable=self._selection, width=240)
            self._menu.pack(pady=(0, 8))
        else:
            self._selection = None
            ctk.CTkLabel(self, text="No robots are currently being monitored.",
                         text_color=SUBTLE_TEXT).pack(pady=(0, 8))

        self._status = ctk.CTkLabel(self, text="", text_color=SUBTLE_TEXT)
        self._status.pack(pady=(0, 8))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=(0, 12))
        self._remove_btn = ctk.CTkButton(
            btns,
            text="Remove",
            width=100,
            fg_color="#CC3333",
            hover_color="#A82828",
            command=self._submit,
            state=("normal" if monitored_robots else "disabled"),
        )
        self._remove_btn.pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Cancel", width=100, fg_color="gray40",
                      command=self.destroy).pack(side="left", padx=6)

        self.wait_visibility()
        self.grab_set()

    def _submit(self):
        if self._selection is None:
            return
        name = self._selection.get()
        try:
            self._on_removed(name)
        except Exception as e:
            self._status.configure(text=f"Failed to remove: {e}", text_color="#CC3333")
            return
        self._status.configure(text=f"{name} removed!", text_color="#2E8B3A")
        self._remove_btn.configure(state="disabled")
        self.after(1200, self._safe_destroy)

    def _safe_destroy(self):
        if self.winfo_exists():
            self.destroy()