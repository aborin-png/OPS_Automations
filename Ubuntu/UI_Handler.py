import pathlib as Path
import json
import os
import threading
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import sys
from types import SimpleNamespace
from git import Repo, InvalidGitRepositoryError

import cv2
from PIL import Image, ImageTk

from Sheets_Automation import Sheets_editor, Decision_matrix, API_fetch, Info_Parser, Zone_scanner
import glossary

# sys.path.insert(0, str(Path.Path(__file__).resolve().parent / "POST_Testing"))
from POST_Testing import Robot_comms
from POST_Testing import robot_password

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

CAMERA_IP_CELL = "10.224.131.2"
CAMERA_IP_DOCK = "10.224.131.7"
CAMERA_USER = "admin"
CAMERA_PASSWORD_CELL = "admin1"
CAMERA_PASSWORD_DOCK = "admin123"
CAMERA_PROFILE = "sub"            # "sub" (640x360 @ 10fps) or "main" (4K @ 25fps)
CAMERA_DEFAULT_CHANNEL = 1        
CAMERA_CHANNELS = glossary.CAMERA_CHANNELS   # robot nickname -> 1-based NVR channel number

VIDEO_W, VIDEO_H = 640, 360

ZONE_NAMES = glossary.ZONE_NAMES
ZONE_TYPES = glossary.ZONE_TYPES


def build_camera_url(channel: int, zone_id=None) -> str:
    # Docks and cells stream from separate Reolink NVRs/IPs. Pick the IP based on the
    # zone's type (defaults to the cell IP for unknown zones).
    ip = CAMERA_IP_DOCK if ZONE_TYPES.get(zone_id) == 'Dock' else CAMERA_IP_CELL
    password = CAMERA_PASSWORD_DOCK if ZONE_TYPES.get(zone_id) == 'Dock' else CAMERA_PASSWORD_CELL
    return f"rtsp://{CAMERA_USER}:{password}@{ip}:554//h264Preview_{channel:02d}_{CAMERA_PROFILE}"




ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def find_config() -> Path.Path:
    start = Path.Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path.Path(__file__).parent
    for directory in [start, *start.parents]:
        
        candidate = directory / 'Config.json'
        if candidate.exists():
            print("Config Found!")
            return candidate
    try:
        repo = Repo(start, search_parent_directories=True)
        path_outside_repo = Path.Path(repo.working_dir).parent / 'Config.json'
    except InvalidGitRepositoryError:
        path_outside_repo = start / 'Config.json' 

    print(f'No Config.json file detected, creating a default at: {path_outside_repo}')
    with open(path_outside_repo, 'w') as config:
        json.dump(glossary.CONFIG_TEMPALTE, config, indent=4)

    return path_outside_repo

CONFIG_PATH = find_config()

TAB_COLORS = {
    "Sheet Editor": "#5B9BD5",
    # "Test Rails":   "#70AD47",
    # "Fault Logging": "#ED7D31",
    "AFSE Monitoring": "#a244eb",
}

STATUS_COLORS = {
    # 1: ('#f20798', 'MAJOR FAULT'),
    0: ("#CC3333", "FAULTED"),
    1: ('#CC3333', 'E-STOPPED'),
    2: ("#CCAA00", "IDLE"),
    3: ("#2E8B3A", "ACTIVE"),
    4: ('#3429ff', 'AUTONOMOUS READY'),
    5: ('#3d3d3d', 'OFFLINE'),
}

CHARGE_STATUS = {
    0: ("#CC3333", 'NOT CHARGING'),
    1: ('#308aff', 'SHORE POWER'),
    2: ('#23cf51', 'MEANWELL CHARGER'),
    3: ('#23cf51', 'ENATEL CHARGER'),
    4: ('#ffeb12', 'INITIALIZING'),
    5: ('#CC3333', 'OFFLINE'),
}

ROBOT_CARD_COLS = 4

ROBOT_OFFLINE = []

#region GUI Window Classes

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("400x300")
        self.resizable(False, False)

        ctk.CTkLabel(self, text="Settings", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        ctk.CTkLabel(self, text="No settings configured yet.", text_color="gray").pack(pady=10)
        ctk.CTkButton(self, text="Close", command=self.destroy).pack(pady=20)

        self.wait_visibility()
        self.grab_set()

class UpdateWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_update):
        super().__init__(parent)
        self.title("OPS Automations Update")
        self.geometry("420x220")
        self.resizable(False, False)

        ctk.CTkLabel(self, text="Update Available", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        self.msg_label = ctk.CTkLabel(self, text="Would you like to update to the latest version?", text_color="gray")
        self.msg_label.pack(pady=10)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)
        self.update_btn = ctk.CTkButton(btn_frame, text="Update", command=lambda: on_update(self))
        self.update_btn.pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="Cancel", command=self.destroy, fg_color="gray40").pack(side="left", padx=8)

        self.wait_visibility()
        self.grab_set()


class ProgressWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Generating Sheet")
        self.geometry("420x150")
        self.resizable(False, False)

        ctk.CTkLabel(self, text="Generating Sheet...", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 10))

        self._progress_bar = ctk.CTkProgressBar(self, width=380)
        self._progress_bar.set(0)
        self._progress_bar.pack(pady=(0, 8), padx=20)

        self._status_label = ctk.CTkLabel(self, text="Starting...", text_color="gray70")
        self._status_label.pack(pady=(0, 16))

        self.wait_visibility()
        self.grab_set()

    def set_progress(self, value: float, message: str):
        self._progress_bar.set(value)
        self._status_label.configure(text=message)

class ConfigUpdateWindow(ctk.CTkToplevel):
    def __init__(self, parent, current_version, required_version, on_update):
        super().__init__(parent)
        self.title("Config Version Mismatch")
        self.geometry("460x280")
        self.resizable(False, False)

        ctk.CTkLabel(self, text="Config Version Mismatch", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 4))

        ver_current = current_version if current_version is not None else "not found"
        ctk.CTkLabel(
            self,
            text=f"Your version: {ver_current}     Required version: {required_version}",
            text_color="gray70"
        ).pack(pady=(0, 12))

        warning_frame = ctk.CTkFrame(self, fg_color="#3d2000", corner_radius=6)
        warning_frame.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(
            warning_frame,
            text="⚠  Updating will overwrite your Config.json.\nBack up any custom changes before continuing.",
            text_color="#ffcc44",
            justify="center",
        ).pack(pady=10, padx=12)

        self.msg_label = ctk.CTkLabel(self, text="")
        self.msg_label.pack(pady=(0, 6))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 16))
        self.update_btn = ctk.CTkButton(btn_frame, text="Update Config", command=lambda: on_update(self))
        self.update_btn.pack(side="left", padx=8)
        self.keep_btn = ctk.CTkButton(btn_frame, text="Keep Current", command=self.destroy, fg_color="gray40")
        self.keep_btn.pack(side="left", padx=8)

        self.wait_visibility()
        self.grab_set()


class AuthWaitWindow(ctk.CTkToplevel):
    '''
    Small status window shown only when robot-password retrieval needs the user to
    authorize in their browser. Starts on a "waiting for authorization" spinner and is
    flipped to a green checkmark once the password is retrieved and the command is sent.
    '''
    def __init__(self, parent, robot_name, action_name):
        super().__init__(parent)
        self.title("Authorization Required")
        self.geometry("440x240")
        self.resizable(False, False)
        self.transient(parent)

        ctk.CTkLabel(self, text=f"{action_name} — {robot_name}", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 8))

        self._icon = ctk.CTkLabel(self, text="⏳", font=ctk.CTkFont(size=40))
        self._icon.pack(pady=(4, 8))

        self._msg = ctk.CTkLabel(
            self,
            text="A browser window was opened.\nPlease click AUTHORIZE to continue.",
            text_color="gray70",
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
    '''
    Dialog for adding a robot to the AFSE monitoring list. Validates the name isn't a
    duplicate, confirms the robot is reachable, then hands the name off to `on_added`
    (which persists it to the config and refreshes the tab).
    '''
    def __init__(self, parent, existing_robots, on_added):
        super().__init__(parent)
        self.title("Add Robot")
        self.geometry("400x240")
        self.resizable(False, False)
        self.transient(parent)
        self._existing = {r.lower() for r in existing_robots}
        self._on_added = on_added

        ctk.CTkLabel(self, text="Add Robot to Monitor", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 8))
        ctk.CTkLabel(self, text="Enter the robot's name (e.g. sb20):", text_color="gray70").pack(pady=(0, 6))

        self._entry = ctk.CTkEntry(self, width=240)
        self._entry.pack(pady=(0, 8))
        self._entry.bind("<Return>", lambda _e: self._submit())

        self._status = ctk.CTkLabel(self, text="", text_color="gray70")
        self._status.pack(pady=(0, 8))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=(0, 12))
        self._add_btn = ctk.CTkButton(btns, text="Add", width=100, command=self._submit)
        self._add_btn.pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Cancel", width=100, fg_color="gray40", command=self.destroy).pack(side="left", padx=6)

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
            self._set_status(f"{name} is not reachable. Check the name and that it's powered on.", "#CC3333")
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
    '''
    Dialog for removing a robot from the AFSE monitoring list. Presents a dropdown of the
    currently monitored robots and hands the chosen name to `on_removed` (which strips it
    from the config and refreshes the tab).
    '''
    def __init__(self, parent, monitored_robots, on_removed):
        super().__init__(parent)
        self.title("Remove Robot")
        self.geometry("400x230")
        self.resizable(False, False)
        self.transient(parent)
        self._on_removed = on_removed

        ctk.CTkLabel(self, text="Remove Monitored Robot", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 8))

        if monitored_robots:
            ctk.CTkLabel(self, text="Select a robot to remove:", text_color="gray70").pack(pady=(0, 6))
            self._selection = ctk.StringVar(value=monitored_robots[0])
            self._menu = ctk.CTkOptionMenu(self, values=list(monitored_robots), variable=self._selection, width=240)
            self._menu.pack(pady=(0, 8))
        else:
            self._selection = None
            ctk.CTkLabel(self, text="No robots are currently being monitored.", text_color="gray70").pack(pady=(0, 8))

        self._status = ctk.CTkLabel(self, text="", text_color="gray70")
        self._status.pack(pady=(0, 8))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=(0, 12))
        self._remove_btn = ctk.CTkButton(
            btns, text="Remove", width=100, fg_color="#CC3333", hover_color="#A82828",
            command=self._submit, state=("normal" if monitored_robots else "disabled"),
        )
        self._remove_btn.pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Cancel", width=100, fg_color="gray40", command=self.destroy).pack(side="left", padx=6)

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


class RobotDetailWindow(ctk.CTkToplevel):
    def __init__(self, parent, robot_name, charge, color_code, charge_code, zone_id=None, camera_channel=CAMERA_DEFAULT_CHANNEL):
        super().__init__(parent)
        self.title(robot_name)
        self._robot_name = robot_name
        self._zone_id = zone_id
        self._camera_url = build_camera_url(camera_channel, zone_id)
        self.geometry("720x860")
        self.resizable(False, False)

        ctk.CTkLabel(self, text=robot_name, font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(16, 8))

        video_container = ctk.CTkFrame(self, width=VIDEO_W, height=VIDEO_H, fg_color="black")
        video_container.pack(pady=(0, 12))
        video_container.pack_propagate(False)
        self.video_label = tk.Label(video_container, bg="black", fg="white", text="Connecting to camera...")
        self.video_label.pack(fill="both", expand=True)

        self.charge_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=32, weight="bold"))
        self.charge_label.pack()
        ctk.CTkLabel(self, text="Charge", text_color="gray70").pack(pady=(0, 4))
        self.charge_status_label = ctk.CTkLabel(self, text="")
        self.charge_status_label.pack(pady=(0, 8))

        self.status_badge = ctk.CTkFrame(self, corner_radius=6)
        self.status_badge.pack(padx=20, pady=(0, 8), fill="x")
        self.status_label = ctk.CTkLabel(self.status_badge, text="", text_color="white", font=ctk.CTkFont(size=14, weight="bold"))
        self.status_label.pack(pady=6)

        self.zone_label = ctk.CTkLabel(self, text="", text_color="gray80", font=ctk.CTkFont(size=20, weight="bold"))
        self.zone_label.pack(pady=(8, 12))

        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(pady=(4, 8))
        ctk.CTkButton(
            action_frame, text="Restart AFSE", width=140,
            command=lambda: self._run_robot_action("Restart AFSE", Robot_comms.restart_AFSE),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            action_frame, text="Stow Robot", width=140,
            command=lambda: self._run_robot_action("Stow Robot", Robot_comms.stow_robot),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            action_frame, text="Reboot Robot", width=140,
            command=lambda: self._run_robot_action("Reboot Robot", Robot_comms.soft_reboot_api),
        ).pack(side="left", padx=4)

        ctk.CTkButton(self, text="Close", command=self._on_close).pack(pady=(4, 12))

        self.update_data(charge, color_code, charge_code, zone_id)

        self._stream_stop = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._photo = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if zone_id and zone_id != 'None':
            threading.Thread(target=self._stream_worker, daemon=True).start()
            self.after(50, self._poll_frame)
        else:
            self.video_label.configure(text="Not connected to Zone")

    def update_data(self, charge, color_code, charge_code, zone_id=None):
        self._zone_id = zone_id
        status_color, status_label = STATUS_COLORS[color_code]
        charge_color, charge_status = CHARGE_STATUS[charge_code]
        self.charge_label.configure(text=f"{charge:.0f}%")
        self.charge_status_label.configure(text=charge_status, text_color=charge_color)
        self.status_badge.configure(fg_color=status_color)
        self.status_label.configure(text=status_label)
        zone_text = ZONE_NAMES.get(zone_id, 'Not in a Zone')
        self.zone_label.configure(text=zone_text)

    def _stream_worker(self):
        cap = cv2.VideoCapture(self._camera_url, cv2.CAP_FFMPEG)
        try:
            while not self._stream_stop.is_set():
                ret, frame = cap.read()
                if not ret:
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil = Image.fromarray(rgb)
                if pil.size != (VIDEO_W, VIDEO_H):
                    pil = pil.resize((VIDEO_W, VIDEO_H), Image.BILINEAR)
                with self._frame_lock:
                    self._latest_frame = pil
        finally:
            cap.release()

    def _poll_frame(self):
        if self._stream_stop.is_set() or not self.winfo_exists():
            return
        with self._frame_lock:
            pil = self._latest_frame
            self._latest_frame = None
        if pil is not None:
            photo = ImageTk.PhotoImage(pil)
            self._photo = photo
            self.video_label.configure(image=photo, text="")
        self.after(50, self._poll_frame)

    def _run_robot_action(self, action_name, action_func):
        # Holds the AuthWaitWindow, which is created lazily and ONLY if browser
        # authorization turns out to be required for the robot password.
        auth_win = {"window": None}

        def on_auth_required():
            def create():
                if self.winfo_exists():
                    auth_win["window"] = AuthWaitWindow(self, self._robot_name, action_name)
            self.after(0, create)

        def finish_success():
            win = auth_win["window"]
            if win is not None and win.winfo_exists():
                win.show_success(f"{action_name} sent to {self._robot_name}.")

        def finish_failure(message):
            win = auth_win["window"]
            if win is not None and win.winfo_exists():
                win.show_failure(message)

        def worker():
            try:
                password = robot_password.get_robot_password(self._robot_name, on_auth_required=on_auth_required)
                if not password:
                    print(f"{action_name}: could not retrieve robot password")
                    self.after(0, lambda: finish_failure("Could not retrieve the robot password."))
                    return
                action_func(self._robot_name, password)
                self.after(0, finish_success)
            except Exception:
                import traceback
                traceback.print_exc()
                self.after(0, lambda: finish_failure("Authorization timed out or the command failed."))
        threading.Thread(target=worker, daemon=True).start()

    def _on_close(self):
        self._stream_stop.set()
        self.destroy()

#endregion

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("OPS Automations")
        self.geometry("900x600")
        self.minsize(700, 450)

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)

        self.config = self.load_config()
        self.authentication = Sheets_editor.authenticator()
        self.load_zone_data()

        self.build_main_area()
        self.build_sidebar()

        self.build_afse_monitoring()
        self.build_Sheet_Editor()

        self.after(300, lambda: threading.Thread(target=self.update_from_git, daemon=True).start())
        self.after(500, self._check_config_version)

        self.protocol("WM_DELETE_WINDOW", self._on_app_close)

    def _on_app_close(self):
        # Cached robot passwords live in memory only; drop them so a reopened GUI re-authorizes.
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

        ctk.CTkLabel(
            self.sidebar, text="Menu", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(16, 8), padx=12)

        ctk.CTkFrame(self.sidebar, height=1, fg_color="gray40").pack(fill="x", padx=12, pady=(0, 12))

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
        # config_path = Decision_matrix.does_config_exist()

        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
        
    def open_settings(self):
        if not hasattr(self, "_settings_win") or not self._settings_win.winfo_exists():
            SettingsWindow(self)

    def load_zone_data(self):
        '''
        Scan the STO "global truth" sheet for the current Zone ID -> Dock/Cell mapping and
        overwrite glossary.ZONE_NAMES / glossary.ZONE_TYPES IN PLACE (so every module that
        imported those dicts sees the live data). Falls back to the hardcoded glossary values
        and warns the user if the scan fails.
        '''
        try:
            zone_names, zone_types = Zone_scanner.scan_zone_data(self.authentication)
            if not zone_names:
                raise ValueError("No zone data found in the STO sheet.")

            glossary.ZONE_NAMES.clear()
            glossary.ZONE_NAMES.update(zone_names)
            glossary.ZONE_TYPES.clear()
            glossary.ZONE_TYPES.update(zone_types)
            print(f"Loaded {len(zone_names)} zones from the STO sheet.")
        except Exception as e:
            print(f"Zone scan failed, using hardcoded fallback: {e}")
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
    def update_from_git(self):
        start_path = Path.Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path.Path(__file__).parent
        try:
            repo = Repo(start_path, search_parent_directories=True)
            origin = repo.remotes.origin
            origin.fetch()

            local_vers = repo.head.commit
            remote_vers = repo.commit('origin/' + repo.active_branch.name)

            if local_vers != remote_vers:
                self.after(0, lambda: UpdateWindow(self, on_update=lambda win: self._start_pull(origin, win)))
        except Exception as e:
            print(f"Git update check failed: {e}")

    def _start_pull(self, origin, win):
        win.update_btn.configure(state="disabled", text="Updating...")
        win.msg_label.configure(text="Pulling latest changes...")
        threading.Thread(target=self._do_pull, args=(origin, win), daemon=True).start()

    def _do_pull(self, origin, win):
        try:
            origin.pull()
            self.after(0, lambda: win.msg_label.configure(text="Update complete. Please restart the application."))
        except Exception as e:
            self.after(0, lambda: win.msg_label.configure(text=f"Update failed: {e}", text_color="#CC3333"))
    
    def _check_config_version(self):
        current = self.config.get("Version")
        required = glossary.CONFIG_VERSION
        if current != required:
            ConfigUpdateWindow(self, current, required, on_update=self._do_config_update)

    def _do_config_update(self, win):
        win.keep_btn.grid_remove()
        win.update_btn.grid_remove()
        with open(CONFIG_PATH, 'w') as f:
            json.dump(glossary.CONFIG_TEMPALTE, f, indent=4)
        self.config = self.load_config()
        win.msg_label.configure(text="Config updated. The application will close soon.", text_color="#2E8B3A")
        
        win.after(1500, win.destroy)
        self.destroy()

#endregion
#----------------------------------------------------------------------------------------------------------------------------------------
############################################################    SHEETS EDITOR    ########################################################
#----------------------------------------------------------------------------------------------------------------------------------------
#region Sheets Editor

#----------------------------------------------------------------------------------------------------------------------------------------


    #region Auxiliary Functions
    
    def get_config_option(self, test_name: str):
        self.selected_option = self.config.get('Options', {}).get(test_name, {})



    def has_template(self, test_name: str) -> bool:
        option = self.config.get("Options", {}).get(test_name, {})
        sheet = option.get("Sheet", {})
        return isinstance(sheet, dict) and "Template" in sheet
    


    def get_sheet_options(self, test_type:str):
        
        self.get_config_option(test_name=test_type)
        sheet = self.selected_option['Sheet']
        print(sheet)
        if isinstance(sheet, dict):
            files = Decision_matrix.multiple_sheets_response(sheet.get('Folder', {}), self.authentication)
            return [[f['name'] for f in files]]
        else:
            return [[sheet]]
        

    def get_worksheet_options(self):
        worksheet = self.selected_option['Worksheet']
        if isinstance(worksheet, dict):
            return [list(worksheet.values())]
        return [[worksheet]]


    def on_test_type_changed(self, _: str):

        test_type = self.test_type_var.get()
        if self.has_template(test_name=test_type):
            self._template_checkbox.grid()
        else:
            self._template_checkbox.grid_remove()
            self._use_template_var.set(False)
            self.on_template_checked()

        self.sheet_options = self.get_sheet_options(test_type=test_type)[0]
        self.sheet_selection = self.sheet_options[0] if self.sheet_options else ""
        self._sheet_type_var.set(self.sheet_selection)
        self._sheet_type_menu.configure(values=self.sheet_options)
        self.sheet_name = self.selected_option.get('Name', '')

        worksheet_options = self.get_worksheet_options()[0]
        self.worksheet_selection = worksheet_options[0] if worksheet_options else ""
        self.worksheet_template_var.set(self.worksheet_selection)
        self._worksheet_menu.configure(values=worksheet_options)

        self.test_data = self.selected_option['Data']
        self._check_generate_ready()
        
    def on_template_checked(self):
        if self._use_template_var.get():
            self._sheet_type_menu.configure(state='disabled')
            self.sheet_selection = self.selected_option['Sheet']['Template']
            self._new_sheet_name_label.grid()
            self._new_sheet_name_entry.grid()
        else:
            self._sheet_type_menu.configure(state='enabled')
            self.sheet_selection = self._sheet_type_var.get()
            self._new_sheet_name_var.set("")
            self._new_sheet_name_label.grid_remove()
            self._new_sheet_name_entry.grid_remove()
        self._check_generate_ready()

    def create_sheet_from_template(self):
        template = self.selected_option['Sheet']['Template']
        name = self._new_sheet_name_var.get().strip()
        if not name:
            return None
        from googleapiclient.discovery import build
        drive = build('drive', 'v3', credentials=self.authentication.http_client.auth)
        new_file = drive.files().copy(
            fileId=template['Key'],
            body={'name': name},
            supportsAllDrives=True
        ).execute()
        return self.authentication.open_by_key(new_file['id'])

    def on_sheet_selection(self, _:str):
        self.sheet_selection = self._sheet_type_var.get()
        self.sheet_data = self.selected_option['Data']
        self.sheet_name = self.selected_option['Name']
        self._check_generate_ready()

    def on_worksheet_selection(self, _:str):
        self.worksheet_selection = self.worksheet_template_var.get()
        self._check_generate_ready()

    def check_robot_online(self):
        nickname = self._robot_entry_var.get().strip().lower()
        if not nickname:
            self.robot_selection = None
            self._robot_status_label.configure(text="", text_color="white")
            self._check_generate_ready()
            return
        self._robot_entry_var.set(nickname)
        self._robot_status_label.configure(text="Checking...", text_color="gray70")
        threading.Thread(target=self._robot_check_worker, args=(nickname,), daemon=True).start()

    def _robot_check_worker(self, nickname):
        result = API_fetch.API_Fetch(nickname, ROBOT_OFFLINE)
        self.after(0, lambda: self._robot_check_result(nickname, result))

    def _robot_check_result(self, nickname, result):
        if result is None:
            self.robot_selection = None
            self._robot_status_label.configure(text="✗ Robot offline or unreachable", text_color="#CC3333")
        else:
            self.robot_selection = nickname
            self._robot_status_label.configure(text="✓ Robot is Online", text_color="#2E8B3A")
        self._check_generate_ready()

    def _check_generate_ready(self):
        robot_ok = bool(getattr(self, 'robot_selection', None))
        sheet_ok = bool(getattr(self, 'sheet_selection', None))
        worksheet_ok = bool(getattr(self, 'worksheet_selection', None))
        template_name_ok = (not self._use_template_var.get()) or bool(self._new_sheet_name_var.get().strip())
        ready = robot_ok and sheet_ok and worksheet_ok and template_name_ok
        self._generate_btn.configure(state="normal" if ready else "disabled")

    def on_generate(self):
        self._generate_btn.configure(state="disabled")
        progress_win = ProgressWindow(self)

        use_template = self._use_template_var.get()
        sheet_title = self.sheet_selection

        def report(value, message):
            def _update():
                if progress_win.winfo_exists():
                    progress_win.set_progress(value, message)
            self.after(0, _update)

        def run():
            completed = [False]
            try:
                report(0.1, "Opening Google Sheet...")
                if use_template:
                    sheet = self.create_sheet_from_template()
                else:
                    sheet = self.authentication.open(title=sheet_title)
                
                print(self.sheet_name)
                Sheets_editor.sheet_editor(
                    self.authentication, sheet, self.worksheet_selection,
                    self.test_data, self.sheet_name, self.robot_selection,
                    progress_cb=report
                )
                completed[0] = True
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Generate failed: {e}")
            finally:
                def _finish():
                    if progress_win.winfo_exists():
                        progress_win.after(800 if completed[0] else 0, progress_win.destroy)
                    self._generate_btn.configure(state="normal")
                self.after(0, _finish)

        threading.Thread(target=run, daemon=True).start()
        

    #endregion


#----------------------------------------------------------------------------------------------------------------------------------------


    #region Main Functions

    def build_Sheet_Editor(self):
        sheet_tab = self.tab_view.tab("Sheet Editor")
        options = list(self.config.get("Options", {}).keys())

        self.sheet_frame = ctk.CTkFrame(sheet_tab, fg_color="gray20")
        self.sheet_frame.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkLabel(self.sheet_frame, text="Test Type:").grid(
            row=0, column=0, padx=(12, 8), pady=12, sticky="w"
        )

        self.test_type_var = ctk.StringVar(value=options[0] if options else "")
        
        self._test_type_menu = ctk.CTkOptionMenu(
            self.sheet_frame,
            values=options,
            variable=self.test_type_var,
            command=self.on_test_type_changed,
        )
        self._test_type_menu.grid(row=0, column=1, padx=(0, 12), pady=12, sticky="w")


        self._use_template_var = ctk.BooleanVar(value=False)
        self._template_checkbox = ctk.CTkCheckBox(
            self.sheet_frame,
            text="Use Template Google Sheet",
            variable=self._use_template_var,
            command=self.on_template_checked
        )
        self._template_checkbox.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="w")
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


        ctk.CTkLabel(self.sheet_frame, text="Sheet:").grid(
            row=2, column=0, padx=(12, 8), pady=(0, 12), sticky="w"
        )
        sheet_options = self.get_sheet_options(test_type=self.test_type_var.get())[0]
        self.sheet_selection = sheet_options[0] if sheet_options else ""
        self.test_data = self.selected_option.get('Data', {})
        self.sheet_name = self.selected_option.get('Name', '')
        self._sheet_type_var = ctk.StringVar(value=self.sheet_selection)
        self._sheet_type_menu = ctk.CTkOptionMenu(
            self.sheet_frame,
            values=sheet_options,
            variable=self._sheet_type_var,
            command=self.on_sheet_selection
        )
        
        self._sheet_type_menu.grid(row=2, column=1, columnspan=2, padx=12, pady=(0, 12), sticky="w")


        ctk.CTkLabel(self.sheet_frame, text="Worksheet:").grid(
            row=3, column=0, padx=(12, 8), pady=(0, 12), sticky="w"
        )
        worksheet_options = self.get_worksheet_options()[0]
        self.worksheet_selection = worksheet_options[0] if worksheet_options else ""
        self.worksheet_template_var = ctk.StringVar(value=self.worksheet_selection)
        self._worksheet_menu = ctk.CTkOptionMenu(
            self.sheet_frame,
            values=worksheet_options,
            variable=self.worksheet_template_var,
            command=self.on_worksheet_selection
        )
        self._worksheet_menu.grid(row=3, column=1, columnspan=2, padx=12, pady=(0, 12), sticky="w")

        ctk.CTkLabel(self.sheet_frame, text="Robot:").grid(
            row=4, column=0, padx=(12, 8), pady=(0, 12), sticky="w"
        )
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

    
#endregion
#----------------------------------------------------------------------------------------------------------------------------------------
############################################################    AFSE MONITORING    ######################################################
#----------------------------------------------------------------------------------------------------------------------------------------
#region AFSE Monitoring

#----------------------------------------------------------------------------------------------------------------------------------------
#Auxiliary Functions

    @staticmethod
    def _dig(obj, path, default=None):
        '''Walk a dotted attribute path safely, returning `default` if any hop is missing.'''
        for attr in path.split('.'):
            obj = getattr(obj, attr, None)
            if obj is None:
                return default
        return obj

    @classmethod
    def _extract_zone_id(cls, data):
        '''
        Safely pull the connected zone id out of the robot data. A robot can report
        zoneState=True while its safetydStatus is missing the zoneId field, so every
        hop is guarded and we fall back to 'None' rather than raising.
        '''
        if not cls._dig(data, 'zoneConnectionStatus.zoneState', False):
            return 'None'
        zone_id = cls._dig(data, 'zoneConnectionStatus.safetydStatus.zoneId')
        return zone_id if zone_id is not None else 'None'

    def get_robot_api(self):
        robot_api = []
        robot_list = self.config['AFSE']['Robots']

        for robot in robot_list:
            # Treat any robot whose API is unreachable OR whose payload is missing
            # expected fields as offline, so one malformed robot can't blank the whole list.
            offline_entry = [robot, 0, 5, 5, 'None']
            try:
                api = API_fetch.API_Fetch(robot, ROBOT_OFFLINE)
                if api is None:
                    raise ValueError("no API response")

                data = Info_Parser.info_parser(api)
                nickname = self._dig(data, 'description.nickname', robot)
                soc = self._dig(data, 'status.battery.soc', 0)
                color = self._dig(data, 'status.lightingState.color', 5)
                charger_mode = self._dig(data, 'status.battery.chargerMode', 5)

                if robot in ROBOT_OFFLINE:
                    ROBOT_OFFLINE.remove(robot)
                robot_api.append([nickname, soc, color, charger_mode, self._extract_zone_id(data)])
            except Exception:
                if robot not in ROBOT_OFFLINE:
                    ROBOT_OFFLINE.append(robot)
                robot_api.append(offline_entry)

        return robot_api
    
    def afse_schedule_refresh(self):
        threading.Thread(target=self.afse_refresh, daemon=True).start()

    def afse_refresh(self):
        robot_api = self.afse_fetch_data()
        self.after(0, lambda: self.afse_apply_refresh(robot_api))

    def afse_apply_refresh(self, robot_api):
        if robot_api is not None:
            # The robot count changes when a robot is added (or first appears), so the
            # card grid has to be rebuilt; otherwise update the existing cards in place.
            if len(robot_api) != len(self.afse_instances):
                self._render_afse_cards(robot_api)
            else:
                self.latest_robot_api = robot_api
                for i, (name, charge, color_code, charge_code, zone_id) in enumerate(robot_api):
                    status_color, status_label = STATUS_COLORS[color_code]
                    charge_color, charge_status = CHARGE_STATUS[charge_code]

                    win = self._robot_detail_windows.get(name)
                    if win is not None and win.winfo_exists():
                        win.update_data(charge, color_code, charge_code, zone_id)

                    self.afse_instances[i][0].configure(text=f'{charge:.0f}%')
                    self.afse_instances[i][1].configure(fg_color=status_color)
                    self.afse_instances[i][2].configure(text=status_label)
                    self.afse_instances[i][3].configure(text= charge_status, text_color= charge_color)
                    zone_text = ZONE_NAMES.get(zone_id, 'Not in a Zone')
                    self.afse_instances[i][4].configure(text=zone_text)
        self.after(5000, self.afse_schedule_refresh)

    def afse_fetch_data(self):
        try:
            robot_api = self.get_robot_api()
        except Exception:
            import traceback
            traceback.print_exc()
            robot_api = None

        return robot_api

#----------------------------------------------------------------------------------------------------------------------------------------
#Main Functions

    def build_afse_monitoring(self):
        afse_tab = self.tab_view.tab('AFSE Monitoring')
        self._afse_cards = []
        self._robot_detail_windows = {}
        self.afse_instances = []
        self.latest_robot_api = []

        header = ctk.CTkFrame(afse_tab, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkButton(header, text="+ Add Robot", width=120, command=self._open_add_robot).pack(side="right")
        ctk.CTkButton(
            header, text="− Remove Robot", width=120, fg_color="gray40", command=self._open_remove_robot
        ).pack(side="right", padx=(0, 8))

        self.afse_frame = ctk.CTkScrollableFrame(afse_tab, fg_color="gray20")
        self.afse_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        for col in range(ROBOT_CARD_COLS):
            self.afse_frame.grid_columnconfigure(col, weight=1)

        self._render_afse_cards(self.afse_fetch_data())
        self.afse_schedule_refresh()

    def _render_afse_cards(self, robot_api):
        '''(Re)build the AFSE card grid from scratch. Used on first build and whenever the
        monitored robot count changes (e.g. a robot was added).'''
        for widget in self._afse_cards:
            widget.destroy()
        self._afse_cards = []
        self.afse_instances = []
        self.latest_robot_api = robot_api or []

        if robot_api is None:
            label = ctk.CTkLabel(self.afse_frame, text="Failed to fetch robot data.", text_color="red")
            label.grid(row=0, column=0, columnspan=ROBOT_CARD_COLS, pady=20)
            self._afse_cards.append(label)
            return

        for i, (name, charge, color_code, charge_code, zone_id) in enumerate(robot_api):
            status_color, status_label = STATUS_COLORS[color_code]
            charge_color, charge_status = CHARGE_STATUS[charge_code]

            card = ctk.CTkFrame(self.afse_frame, fg_color="gray30", corner_radius=8)
            card.grid(row=i // ROBOT_CARD_COLS, column=i % ROBOT_CARD_COLS, padx=8, pady=8, sticky="nsew")
            self._afse_cards.append(card)

            ctk.CTkLabel(card, text=name, font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 4), padx=12)

            robot_charge = ctk.CTkLabel(card, text=f"{charge:.0f}%", font=ctk.CTkFont(size=24, weight="bold"))
            robot_charge.pack(pady=(4, 0))
            ctk.CTkLabel(card, text="Charge", text_color="gray70", font=ctk.CTkFont(size=11)).pack(pady=(0, 8))
            robot_charge_status = ctk.CTkLabel(card, text=charge_status, text_color= charge_color, font=ctk.CTkFont(size=11))
            robot_charge_status.pack(pady=(0, 8))

            status_badge = ctk.CTkFrame(card, fg_color=status_color, corner_radius=6)
            status_badge.pack(pady=(0, 6), padx=12, fill="x")
            robot_status = ctk.CTkLabel(status_badge, text=status_label, text_color="white", font=ctk.CTkFont(size=12, weight="bold"))
            robot_status.pack(pady=6)

            zone_text = ZONE_NAMES.get(zone_id, 'Not in a Zone')
            robot_zone = ctk.CTkLabel(card, text=zone_text, text_color="gray80", font=ctk.CTkFont(size=12))
            robot_zone.pack(pady=(0, 10))

            self.afse_instances.append([robot_charge, status_badge, robot_status, robot_charge_status, robot_zone])
            self._bind_card_click(card, i)

    def _open_add_robot(self):
        if getattr(self, "_add_robot_win", None) is not None and self._add_robot_win.winfo_exists():
            self._add_robot_win.focus()
            return
        self._add_robot_win = AddRobotWindow(self, self.config['AFSE']['Robots'], self._add_robot_to_config)

    def _add_robot_to_config(self, name):
        '''Persist a new robot to the config's AFSE list and refresh the tab. Runs on the
        main thread (invoked from AddRobotWindow after a successful reachability check).'''
        self.config['AFSE']['Robots'].append(name)
        with open(CONFIG_PATH, 'w') as f:
            json.dump(self.config, f, indent=4)
        self._reload_afse()

    def _open_remove_robot(self):
        if getattr(self, "_remove_robot_win", None) is not None and self._remove_robot_win.winfo_exists():
            self._remove_robot_win.focus()
            return
        self._remove_robot_win = RemoveRobotWindow(self, self.config['AFSE']['Robots'], self._remove_robot_from_config)

    def _remove_robot_from_config(self, name):
        '''Strip a robot from the config's AFSE list, persist, and refresh the tab.'''
        robots = self.config['AFSE']['Robots']
        if name in robots:
            robots.remove(name)
        if name in ROBOT_OFFLINE:
            ROBOT_OFFLINE.remove(name)
        with open(CONFIG_PATH, 'w') as f:
            json.dump(self.config, f, indent=4)
        self._reload_afse()

    def _reload_afse(self):
        '''One-shot fetch + re-render so a newly added robot shows immediately, without
        starting a second refresh loop (the existing 5s loop keeps running).'''
        def work():
            robot_api = self.afse_fetch_data()
            self.after(0, lambda: self._render_afse_cards(robot_api))
        threading.Thread(target=work, daemon=True).start()

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

    def _open_robot_window(self, index):
        if index >= len(self.latest_robot_api):
            return
        name, charge, color_code, charge_code, zone_id = self.latest_robot_api[index]
        existing = self._robot_detail_windows.get(name)
        if existing is not None and existing.winfo_exists():
            existing.focus()
            return
        channel = CAMERA_CHANNELS.get(zone_id, CAMERA_DEFAULT_CHANNEL)
        self._robot_detail_windows[name] = RobotDetailWindow(self, name, charge, color_code, charge_code, zone_id=zone_id, camera_channel=channel)



#endregion    


if __name__ == "__main__":
    app = App()
    app.mainloop()
