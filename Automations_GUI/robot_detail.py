# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""The per-robot detail window (live camera feed + status + robot action buttons).

Opened by clicking a robot card in the AFSE monitoring tab (see UI_Handler.py). Kept separate from
UI_Handler.py because of its size and its self-contained RTSP video-streaming logic.
"""
import logging
import os
import threading
import tkinter as tk

import customtkinter as ctk
import cv2
import glossary
import logger_setup
from API_Post import Robot_comms, robot_password
from dialogs import AuthWaitWindow
from logger_setup import log_calls
from PIL import Image, ImageTk

# Force the FFMPEG backend to use TCP for RTSP (more reliable than the default UDP for the Reolink
# NVR streams). Must be set before any cv2.VideoCapture(..., CAP_FFMPEG) call.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# Configuration constants live in glossary.py (single source of truth); aliased here so the code
# below stays short. See glossary.py for descriptions of each.
CAMERA_IP_CELL = glossary.CAMERA_IP_CELL
CAMERA_IP_DOCK = glossary.CAMERA_IP_DOCK
CAMERA_USER = glossary.CAMERA_USER
CAMERA_PASSWORD_CELL = glossary.CAMERA_PASSWORD_CELL
CAMERA_PASSWORD_DOCK = glossary.CAMERA_PASSWORD_DOCK
CAMERA_PROFILE = glossary.CAMERA_PROFILE
CAMERA_DEFAULT_CHANNEL = glossary.CAMERA_DEFAULT_CHANNEL
VIDEO_W, VIDEO_H = glossary.VIDEO_W, glossary.VIDEO_H
STATUS_COLORS = glossary.STATUS_COLORS
CHARGE_STATUS = glossary.CHARGE_STATUS
SUBTLE_TEXT = glossary.SUBTLE_TEXT
# ZONE_NAMES / ZONE_TYPES are overwritten IN PLACE on startup (see UI_Handler.load_zone_data), so
# these aliases keep pointing at the live dicts.
ZONE_NAMES = glossary.ZONE_NAMES
ZONE_TYPES = glossary.ZONE_TYPES

# Same configured "OPS" logger that UI_Handler set up via logger_setup.setup_logging().
logger = logging.getLogger(logger_setup.LOGGER_NAME)


def build_camera_url(channel: int, zone_id=None) -> str:
    # Docks and cells stream from separate Reolink NVRs/IPs. Pick the IP based on the
    # zone's type (defaults to the cell IP for unknown zones).
    ip = CAMERA_IP_DOCK if ZONE_TYPES.get(zone_id) == 'Dock' else CAMERA_IP_CELL
    password = CAMERA_PASSWORD_DOCK if ZONE_TYPES.get(zone_id) == 'Dock' else CAMERA_PASSWORD_CELL
    return f"rtsp://{CAMERA_USER}:{password}@{ip}:554//h264Preview_{channel:02d}_{CAMERA_PROFILE}"


class RobotDetailWindow(ctk.CTkToplevel):
    """Detailed per-robot view opened by clicking an AFSE monitoring card.

    Shows the robot's live camera feed (RTSP from the zone's Reolink NVR, streamed on a background
    thread) alongside charge, status, and zone readouts that are refreshed in place via
    `update_data`. Also provides action buttons (Restart AFSE, Stow Robot, Reboot Robot) that
    retrieve the robot password and issue the command through Robot_comms, surfacing an
    AuthWaitWindow if browser authorization is required.
    """

    def __init__(self, parent, robot_name, charge, color_code, charge_code, zone_id=None,
                 camera_channel=CAMERA_DEFAULT_CHANNEL):
        super().__init__(parent)
        self.title(robot_name)
        self._robot_name = robot_name
        self._zone_id = zone_id
        self._camera_url = build_camera_url(camera_channel, zone_id)
        self.geometry("720x860")
        self.resizable(False, False)

        ctk.CTkLabel(self, text=robot_name, font=ctk.CTkFont(size=20,
                                                             weight="bold")).pack(pady=(16, 8))

        video_container = ctk.CTkFrame(self, width=VIDEO_W, height=VIDEO_H, fg_color="black")
        video_container.pack(pady=(0, 12))
        video_container.pack_propagate(False)
        self.video_label = tk.Label(video_container, bg="black", fg="white",
                                    text="Connecting to camera...")
        self.video_label.pack(fill="both", expand=True)

        self.charge_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=32, weight="bold"))
        self.charge_label.pack()
        ctk.CTkLabel(self, text="Charge", text_color=SUBTLE_TEXT).pack(pady=(0, 4))
        self.charge_status_label = ctk.CTkLabel(self, text="")
        self.charge_status_label.pack(pady=(0, 8))

        self.status_badge = ctk.CTkFrame(self, corner_radius=6)
        self.status_badge.pack(padx=20, pady=(0, 8), fill="x")
        self.status_label = ctk.CTkLabel(self.status_badge, text="", text_color="white",
                                         font=ctk.CTkFont(size=14, weight="bold"))
        self.status_label.pack(pady=6)

        self.zone_label = ctk.CTkLabel(self, text="", text_color=SUBTLE_TEXT,
                                       font=ctk.CTkFont(size=20, weight="bold"))
        self.zone_label.pack(pady=(8, 12))

        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(pady=(4, 8))
        ctk.CTkButton(
            action_frame,
            text="Restart AFSE",
            width=140,
            command=lambda: self._run_robot_action("Restart AFSE", Robot_comms.restart_AFSE),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            action_frame,
            text="Stow Robot",
            width=140,
            command=lambda: self._run_robot_action("Stow Robot", Robot_comms.stow_robot),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            action_frame,
            text="Reboot Robot",
            width=140,
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

    @log_calls
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
                password = robot_password.get_robot_password(self._robot_name,
                                                             on_auth_required=on_auth_required)
                if not password:
                    logger.warning("%s: could not retrieve password for %s", action_name,
                                   self._robot_name)
                    self.after(0, lambda: finish_failure("Could not retrieve the robot password."))
                    return
                action_func(self._robot_name, password)
                self.after(0, finish_success)
            except Exception:
                logger.exception("Robot action '%s' failed for %s", action_name, self._robot_name)
                self.after(0,
                           lambda: finish_failure("Authorization timed out or the command failed."))

        threading.Thread(target=worker, daemon=True).start()

    def _on_close(self):
        self._stream_stop.set()
        self.destroy()