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
        self.geometry("400x400")
        self.resizable(False, True)

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

        ctk.CTkLabel(self, text="Fullscreen Mode", text_color=SUBTLE_TEXT).pack(pady=(4, 2))
        self._fullscreen_var = ctk.IntVar(value=self._app.fullscreen)
        ctk.CTkCheckBox(self, text="Fullscreen", variable=self._fullscreen_var,
                        command=self._fullscreen_mode_changed, onvalue=1,
                        offvalue=0).pack(pady=(0, 4))

        ctk.CTkButton(self, text="Close", command=self.destroy).pack(pady=(8, 20))

        self.wait_visibility()
        self.grab_set()

    def _on_scaling_change(self, choice):
        factor = int(choice.rstrip('%')) / 100.0
        self._app.set_ui_scaling(factor)

    def _appearance_mode_changed(self, choice):
        ctk.set_appearance_mode(choice)

    def _fullscreen_mode_changed(self):
        self._app.set_fullscreen_setting(self._fullscreen_var.get())


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

    Explains that updating merges new template defaults into their config while keeping their
    customizations (a backup is saved first), and offers to run the merge (`on_update`) or keep the
    current config as-is.
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

        info_frame = ctk.CTkFrame(self, fg_color="#12331d", corner_radius=6)
        info_frame.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(
            info_frame,
            text="Updating merges new defaults into your config while keeping your\n"
            "customizations (Options, robots, settings). A backup is saved first.",
            text_color="#7fdca0",
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


class PasswordUnlockWindow(ctk.CTkToplevel):
    """Prompts for the shared key to unlock the robot-password store, then doubles as the status
    window for the robot action that triggered it.

    Shown only when the store isn't already unlocked this session (mirrors how the old browser-auth
    window appeared only when an extra step was needed). Two phases:

      1. **Key entry** -- a masked field. On submit ``validate(key)`` runs (it decrypts the store and
         returns it, or raises with a user-facing message); a wrong/malformed key shows an inline
         error and the field stays open to try again. ``on_resolved`` is called exactly once -- with
         the decrypted store on success, or ``None`` if the user cancels -- which is how the waiting
         worker thread is released.
      2. **Action status** -- after a successful unlock the window switches to a "sending..." state
         and the caller drives ``show_success`` / ``show_failure`` for the action itself.
    """

    def __init__(self, parent, robot_name, action_name, validate, on_resolved):
        super().__init__(parent)
        self.title("Unlock Robot Passwords")
        self.geometry("470x300")
        self.resizable(False, False)
        self.transient(parent)
        self._validate = validate
        self._on_resolved = on_resolved
        self._resolved = False

        ctk.CTkLabel(self, text=f"{action_name} — {robot_name}",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 4))

        self._msg = ctk.CTkLabel(
            self,
            text="Enter the shared key to unlock robot passwords for this session.",
            text_color=SUBTLE_TEXT,
            wraplength=430,
            justify="center",
        )
        self._msg.pack(pady=(0, 10))

        self._entry_var = ctk.StringVar()
        self._entry = ctk.CTkEntry(self, textvariable=self._entry_var, width=390, show="•",
                                   placeholder_text="AGE-SECRET-KEY-...")
        self._entry.pack(pady=(0, 8))
        self._entry.bind("<Return>", lambda _e: self._submit())

        self._status = ctk.CTkLabel(self, text="", text_color=SUBTLE_TEXT, wraplength=430,
                                    justify="center")
        self._status.pack(pady=(0, 8))

        # Phase-2/3 widgets, created now but packed only when we reach those phases.
        self._bar = ctk.CTkProgressBar(self, width=320, mode="indeterminate")
        self._icon = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=36))
        self._close_btn = ctk.CTkButton(self, text="Close", fg_color="gray40",
                                        command=self._safe_destroy)

        self._btns = ctk.CTkFrame(self, fg_color="transparent")
        self._btns.pack(pady=(0, 12))
        self._submit_btn = ctk.CTkButton(self._btns, text="Unlock", width=110, command=self._submit)
        self._submit_btn.pack(side="left", padx=6)
        ctk.CTkButton(self._btns, text="Cancel", width=110, fg_color="gray40",
                      command=self._cancel).pack(side="left", padx=6)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.wait_visibility()
        self.grab_set()
        self._entry.focus()

    def _resolve(self, result):
        """Release the waiting worker with ``result`` (the store, or None).

        Fires at most once.
        """
        if self._resolved:
            return
        self._resolved = True
        self._on_resolved(result)

    def _submit(self):
        key = self._entry_var.get().strip()
        if not key:
            self._status.configure(text="Please paste the shared key.", text_color="#CC3333")
            return
        self._submit_btn.configure(state="disabled")
        self._entry.configure(state="disabled")
        self._status.configure(text="Unlocking...", text_color=SUBTLE_TEXT)
        self.update_idletasks()
        try:
            store = self._validate(key)
        except Exception as e:  # noqa: BLE001 -- PasswordStoreError et al.; message is user-facing
            self._submit_btn.configure(state="normal")
            self._entry.configure(state="normal")
            self._status.configure(text=str(e), text_color="#CC3333")
            self._entry.focus()
            return
        self._resolve(store)
        self._enter_working_phase()

    def _cancel(self):
        self._resolve(None)
        self._safe_destroy()

    def _enter_working_phase(self):
        self._entry.pack_forget()
        self._btns.pack_forget()
        self._msg.configure(text="Passwords unlocked. Sending command...", text_color=SUBTLE_TEXT)
        self._status.configure(text="")
        self._bar.pack(pady=(4, 14), padx=20)
        self._bar.start()

    def show_success(self, message):
        if not self.winfo_exists():
            return
        self._bar.stop()
        self._bar.pack_forget()
        self._icon.configure(text="✓", text_color="#2E8B3A")
        self._icon.pack(pady=(4, 8))
        self._msg.configure(text=message, text_color="#2E8B3A")
        self._close_btn.pack(pady=(0, 14))
        self.after(4000, self._safe_destroy)

    def show_failure(self, message):
        if not self.winfo_exists():
            return
        self._bar.stop()
        self._bar.pack_forget()
        self._icon.configure(text="✕", text_color="#CC3333")
        self._icon.pack(pady=(4, 8))
        self._msg.configure(text=message, text_color="#CC3333")
        self._close_btn.pack(pady=(0, 14))

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


class SheetLogWindow(ctk.CTkToplevel):
    """Prompt for a message to log to the sheet -- a RETRO or a plain comment.

    The user types a message and presses Enter / Submit; leaving it blank lets the caller assign a
    sequential default (``Retro N`` / ``Comment N``). ``on_submit(window, message_text)`` is invoked
    with the raw (possibly empty) text and this window, so the caller can run the send in a worker
    thread and drive ``finish_success`` / ``finish_failure`` back on the main thread. Title, heading
    and placeholder are supplied by the caller so the one window serves both features.
    """

    def __init__(self, parent, target_label, on_submit, *, title="RETRO", heading="Log a RETRO",
                 placeholder="Message (blank = 'Retro N')"):
        super().__init__(parent)
        self.title(title)
        self.geometry("460x260")
        self.resizable(False, False)
        self.transient(parent)
        self._on_submit = on_submit
        self._working = False

        ctk.CTkLabel(self, text=heading, font=ctk.CTkFont(size=16,
                                                          weight="bold")).pack(pady=(20, 4))
        ctk.CTkLabel(self, text=target_label, text_color=SUBTLE_TEXT, wraplength=420,
                     justify="center").pack(pady=(0, 10))

        self._entry_var = ctk.StringVar()
        self._entry = ctk.CTkEntry(self, textvariable=self._entry_var, width=360,
                                   placeholder_text=placeholder)
        self._entry.pack(pady=(0, 8))
        self._entry.bind("<Return>", lambda _e: self._submit())

        self._status = ctk.CTkLabel(self, text="", text_color=SUBTLE_TEXT, wraplength=420,
                                    justify="center")
        self._status.pack(pady=(0, 8))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=(0, 12))
        self._submit_btn = ctk.CTkButton(btns, text="Submit", width=110, command=self._submit)
        self._submit_btn.pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Cancel", width=110, fg_color="gray40",
                      command=self.destroy).pack(side="left", padx=6)

        self.wait_visibility()
        self.grab_set()
        self._entry.focus()

    def _submit(self):
        if self._working:
            return
        self._working = True
        self._submit_btn.configure(state="disabled")
        self._entry.configure(state="disabled")
        self._status.configure(text="Sending retro...", text_color=SUBTLE_TEXT)
        self._on_submit(self, self._entry_var.get().strip())

    def finish_success(self, message):
        if not self.winfo_exists():
            return
        self._status.configure(text=message, text_color="#2E8B3A")
        self.after(1500, self._safe_destroy)

    def finish_failure(self, message):
        if not self.winfo_exists():
            return
        self._working = False
        self._submit_btn.configure(state="normal")
        self._entry.configure(state="normal")
        self._status.configure(text=message, text_color="#CC3333")

    def _safe_destroy(self):
        if self.winfo_exists():
            self.destroy()
