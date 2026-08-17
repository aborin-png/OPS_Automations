# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Behaviour / logic for the "Sheet Editor" tab.

This is a mixin whose methods become part of the App class (see UI_Handler.py). It holds only the
tab's *functionality* -- config option lookups, dropdown/checkbox handlers, robot reachability
checks, and the sheet-generation worker. The widgets themselves are built by
``App.build_Sheet_Editor`` in UI_Handler.py, which is why every method here operates on ``self``
(the App instance) and its widget attributes.
"""
import datetime
import logging
import threading
from tkinter import messagebox

import glossary
import gspread
import logger_setup
from dialogs import ImageBannerReminderWindow, ImageUploadWindow, ProgressWindow, SheetLogWindow
from gspread.utils import rowcol_to_a1
from logger_setup import log_calls
from Sheets_Automation import API_fetch, Drive_Images, RETRO_Logging, Sheets_editor

# How many recently-created worksheets to keep in the RETRO history (persisted to the config).
RETRO_HISTORY_LIMIT = 50

SUBTLE_TEXT = glossary.SUBTLE_TEXT
# Same configured "OPS" logger that UI_Handler set up via logger_setup.setup_logging().
logger = logging.getLogger(logger_setup.LOGGER_NAME)

# ----------------------------------------------------------------------------------------------
#region Sheet Editor Mixin
# ----------------------------------------------------------------------------------------------


class SheetEditorMixin:
    """Sheet Editor tab logic.

    Mixed into App; relies on widgets built by build_Sheet_Editor.
    """

    def get_config_option(self, test_name: str):
        self.selected_option = self.config.get('Options', {}).get(test_name, {})

    def has_template(self, test_name: str) -> bool:
        option = self.config.get("Options", {}).get(test_name, {})
        sheet = option.get("Sheet", {})
        return isinstance(sheet, dict) and "Template" in sheet

    def get_sheet_options(self, test_type: str):

        self.get_config_option(test_name=test_type)
        sheet = self.selected_option['Sheet']
        logger.debug("Sheet option for %s: %s", test_type, sheet)
        if isinstance(sheet, dict):
            files = Sheets_editor.multiple_sheets_response(sheet.get('Folder', {}),
                                                           self.authentication)
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

    def refresh_test_types(self):
        """Re-sync the Test Type dropdown with config["Options"] after the Config Editing tab adds,
        edits, or removes an option.

        Always re-runs on_test_type_changed for the resulting selection so an *edit* to the
        currently-selected type is reflected too; if the selected type was removed/renamed, falls
        back to the first remaining option.
        """
        options = list(self.config.get("Options", {}).keys())
        self._test_type_menu.configure(values=options)
        current = self.test_type_var.get()
        target = current if current in options else (options[0] if options else "")
        if target != current:
            self.test_type_var.set(target)
        if target:
            self.on_test_type_changed(target)

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

    @log_calls
    def create_sheet_from_template(self):
        template = self.selected_option['Sheet']['Template']
        name = self._new_sheet_name_var.get().strip()
        if not name:
            return None
        from googleapiclient.discovery import build
        drive = build('drive', 'v3', credentials=self.authentication.http_client.auth)
        new_file = drive.files().copy(fileId=template['Key'], body={
            'name': name
        }, supportsAllDrives=True).execute()
        return self.authentication.open_by_key(new_file['id'])

    def on_sheet_selection(self, _: str):
        self.sheet_selection = self._sheet_type_var.get()
        self.sheet_data = self.selected_option['Data']
        self.sheet_name = self.selected_option['Name']
        self._check_generate_ready()

    def on_worksheet_selection(self, _: str):
        self.worksheet_selection = self.worksheet_template_var.get()
        self._check_generate_ready()

    @log_calls
    def check_robot_online(self):
        nickname = self._robot_entry_var.get().strip().lower()
        if not nickname:
            self.robot_selection = None
            self._robot_status_label.configure(text="", text_color="white")
            self._check_generate_ready()
            return
        self._robot_entry_var.set(nickname)
        self._robot_status_label.configure(text="Checking...", text_color=SUBTLE_TEXT)
        threading.Thread(target=self._robot_check_worker, args=(nickname,), daemon=True).start()

    def _robot_check_worker(self, nickname):
        result = API_fetch.API_Fetch(nickname, self.robot_offline)
        self.after(0, lambda: self._robot_check_result(nickname, result))

    def _robot_check_result(self, nickname, result):
        if result is None:
            self.robot_selection = None
            self._robot_status_label.configure(text="✗ Robot offline or unreachable",
                                               text_color="#CC3333")
        else:
            self.robot_selection = nickname
            self._robot_status_label.configure(text="✓ Robot is Online", text_color="#2E8B3A")
        self._check_generate_ready()
        # A "Specific" RETRO takes its robot from this field, so re-evaluate its target + buttons.
        self._update_retro_target_label()
        self._update_retro_button()

    def _check_generate_ready(self):
        robot_ok = bool(getattr(self, 'robot_selection', None))
        sheet_ok = bool(getattr(self, 'sheet_selection', None))
        worksheet_ok = bool(getattr(self, 'worksheet_selection', None))
        template_name_ok = (not self._use_template_var.get()) or bool(
            self._new_sheet_name_var.get().strip())
        ready = robot_ok and sheet_ok and worksheet_ok and template_name_ok
        self._generate_btn.configure(state="normal" if ready else "disabled")

    @log_calls
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

                logger.info("Generating sheet '%s' for %s", self.sheet_name, self.robot_selection)
                created_ws = Sheets_editor.sheet_editor(self.authentication, sheet,
                                                        self.worksheet_selection, self.test_data,
                                                        self.sheet_name, self.robot_selection,
                                                        progress_cb=report)
                if created_ws is not None:
                    entry = self._build_retro_entry(sheet, created_ws, self.robot_selection)
                    self.after(0, lambda e=entry: self.record_created_worksheet(e))
                completed[0] = True
            except Exception:
                logger.exception("Sheet generation failed")
            finally:

                def _finish():
                    if progress_win.winfo_exists():
                        progress_win.after(800 if completed[0] else 0, progress_win.destroy)
                    self._generate_btn.configure(state="normal")

                self.after(0, _finish)

        threading.Thread(target=run, daemon=True).start()

    # ----------------------------------------------------------------------------------------------
    #region RETRO logging
    # ----------------------------------------------------------------------------------------------
    @log_calls
    def load_retro_sheet(self):
        """Open the sheet named in the RETRO 'Sheet title' box and populate the tab dropdown with
        its worksheets (used by the 'Specific' worksheet source).

        Runs the network open in a worker thread so the UI stays responsive.
        """
        title = self._retro_sheet_var.get().strip()
        if not title:
            self._retro_load_status.configure(text="Enter a sheet title first.",
                                              text_color="#CC3333")
            return
        self._retro_load_btn.configure(state="disabled")
        self._retro_load_status.configure(text="Loading tabs...", text_color=SUBTLE_TEXT)
        threading.Thread(target=self._retro_load_worker, args=(title,), daemon=True).start()

    def _retro_load_worker(self, title):
        try:
            sheet = self.authentication.open(title=title)
            tabs = [(ws.title, ws.id, ws.url) for ws in sheet.worksheets()]
            loaded = {
                "key": sheet.id,
                "title": sheet.title,
                "tabs": {
                    t: {
                        "id": wid,
                        "url": url
                    } for t, wid, url in tabs
                },
            }
            titles = [t for t, _, _ in tabs]
            self.after(0, lambda: self._retro_load_done(loaded, titles))
        except gspread.exceptions.SpreadsheetNotFound:
            self.after(0, lambda: self._retro_load_failed(f"No sheet titled '{title}' found."))
        except Exception as e:  # noqa: BLE001 -- surfaced to the user below
            logger.exception("Failed to load RETRO worksheet tabs")
            self.after(0, lambda err=e: self._retro_load_failed(f"Could not load tabs: {err}"))

    def _retro_load_done(self, loaded, titles):
        self._retro_loaded_sheet = loaded
        self._retro_load_btn.configure(state="normal")
        self._retro_tab_menu.configure(values=titles or ["(no tabs)"])
        self._retro_tab_var.set(titles[0] if titles else "(no tabs)")
        self._retro_load_status.configure(
            text=f"Loaded {len(titles)} tab(s) from '{loaded['title']}'.", text_color="#2E8B3A")
        self._update_retro_target_label()
        self._update_retro_button()

    def _retro_load_failed(self, message):
        self._retro_loaded_sheet = None
        self._retro_load_btn.configure(state="normal")
        self._retro_tab_menu.configure(values=["(load a sheet)"])
        self._retro_tab_var.set("(load a sheet)")
        self._retro_load_status.configure(text=message, text_color="#CC3333")
        self._update_retro_target_label()
        self._update_retro_button()

    def _retro_history(self) -> list:
        """The persisted list of recently created worksheets (created lazily in the config)."""
        return self.config.setdefault("RetroWorksheets", [])

    @staticmethod
    def _build_retro_entry(sheet, worksheet, robot) -> dict:
        """Identifying info for a created worksheet -- enough to reopen it and target its robot.

        Built from cached gspread attributes (no network), so it's safe to call from a worker.
        """
        return {
            "spreadsheet_key": sheet.id,
            "spreadsheet_title": sheet.title,
            "worksheet_id": worksheet.id,
            "worksheet_title": worksheet.title,
            "robot": robot,
            "url": worksheet.url,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }

    def record_created_worksheet(self, entry: dict):
        """Append a created worksheet to the RETRO history, persist it, and refresh the controls.

        Runs on the main thread (scheduled from the generate worker). De-dupes by spreadsheet +
        worksheet id, so re-recording the same tab just moves it to the most-recent slot.
        """
        history = self._retro_history()
        history[:] = [
            e for e in history
            if (e.get("spreadsheet_key"), e.get("worksheet_id")) != (entry["spreadsheet_key"],
                                                                     entry["worksheet_id"])
        ]
        history.append(entry)
        del history[:-RETRO_HISTORY_LIMIT]  # keep only the most-recent RETRO_HISTORY_LIMIT entries
        self.save_config()
        self.refresh_retro_controls()
        logger.info("Recorded created worksheet %r for the RETRO history.",
                    entry["worksheet_title"])

    def refresh_retro_controls(self):
        """Refresh the target label + buttons.

        Called after a Generate (a new worksheet is recorded, which "Latest" points at) and once at
        build time. "Specific" is driven separately by load_retro_sheet / the tab dropdown.
        """
        self._update_retro_target_label()
        self._update_retro_button()

    def _resolve_retro_target(self):
        """The worksheet the RETRO / Comment will act on, or None if nothing is targetable yet.

        "Latest" uses the most recently generated worksheet from the history (which carries the
        robot it was generated for). "Specific" uses the tab chosen from a manually loaded sheet,
        taking the robot from the Sheet Editor's Robot field, since a manually picked sheet has no
        generation history to supply one.
        """
        if self._retro_source_var.get() == "Specific":
            loaded = self._retro_loaded_sheet
            if not loaded:
                return None
            info = loaded["tabs"].get(self._retro_tab_var.get())
            if info is None:
                return None
            return {
                "spreadsheet_key": loaded["key"],
                "spreadsheet_title": loaded["title"],
                "worksheet_id": info["id"],
                "worksheet_title": self._retro_tab_var.get(),
                "robot": getattr(self, "robot_selection", None),
                "url": info["url"],
            }
        history = self._retro_history()
        return history[-1] if history else None

    def _update_retro_target_label(self):
        entry = self._resolve_retro_target()
        if entry is None:
            if self._retro_source_var.get() == "Specific":
                msg = "Load a sheet and choose a tab."
            else:
                msg = "No created worksheets yet — generate a sheet first."
            self._retro_target_label.configure(text=msg, text_color=SUBTLE_TEXT)
        else:
            robot = entry.get("robot") or "enter a robot above"
            self._retro_target_label.configure(text=f'→ {robot}  ·  {entry["worksheet_title"]}',
                                               text_color=SUBTLE_TEXT)

    def _update_retro_button(self):
        entry = self._resolve_retro_target()
        targetable = entry is not None
        has_robot = bool(entry and entry.get("robot"))
        # A comment (and an image) only write to the sheet, so they just need a target; a RETRO also
        # POSTs to the robot, so it additionally needs one (always present for "Latest"; from the
        # Robot field for "Specific").
        self._comment_btn.configure(state="normal" if targetable else "disabled")
        self._retro_btn.configure(state="normal" if (targetable and has_robot) else "disabled")
        self._image_btn.configure(state="normal" if targetable else "disabled")

    def on_retro_source_changed(self, mode: str):
        if mode == "Specific":
            self._retro_specific_frame.grid()
        else:
            self._retro_specific_frame.grid_remove()
        self._update_retro_target_label()
        self._update_retro_button()

    def on_retro_tab_selected(self, _: str):
        self._update_retro_target_label()
        self._update_retro_button()

    @log_calls
    def open_retro_window(self):
        self._open_log_window("retro")

    @log_calls
    def open_comment_window(self):
        self._open_log_window("comment")

    def _open_log_window(self, kind: str):
        """Open the message prompt for a RETRO or a plain comment.

        Both target the currently selected worksheet; the difference is handled in ``_send_log``
        (only a retro POSTs the comment to the robot and ticks the Retro checkbox). For a retro we
        additionally fire the data-capturing retro-log *immediately* -- the instant the window opens,
        not on submit -- so the event's recent-data window isn't lost while the user composes their
        message (see _fire_retro_log).
        """
        entry = self._resolve_retro_target()
        if entry is None:
            return
        target = f'{entry.get("robot") or "—"}  ·  {entry["worksheet_title"]}'
        if kind == "retro":
            title, heading, placeholder = "RETRO", "Log a RETRO", "Message (blank = 'Retro N')"
        else:
            title, heading, placeholder = "Comment", "Add a Comment", "Comment (blank = 'Comment N')"
        window = SheetLogWindow(self, target_label=target, title=title, heading=heading,
                                placeholder=placeholder,
                                on_submit=lambda win, text: self._send_log(entry, text, win, kind),
                                kind=kind)
        if kind == "retro":
            self._fire_retro_log(entry, window)
        return window

    def _fire_retro_log(self, entry: dict, window):
        """POST the retro-log to the robot right now, in a worker thread, so pressing RETRO captures
        the event's recent-data window immediately -- before the user spends time typing.

        The message-bearing comment is sent later, on submit (_send_log). The capture's outcome is
        reported back into the window's status line (unless the user has already submitted).
        """
        robot = entry.get("robot")
        if not robot:
            return  # a retro always has a robot (the RETRO button is disabled otherwise); guard anyway

        def worker():
            try:
                RETRO_Logging.take_retro_log(f"{robot}.stretch")
                logger.info("Retro-log captured for %r.", robot)
                self.after(0, lambda: window.set_capture_result(True))
            except Exception as e:  # noqa: BLE001 -- reported in the window / logged
                logger.exception("Retro-log capture failed for %r", robot)
                self.after(0, lambda err=e: window.set_capture_result(False, str(err)))

        threading.Thread(target=worker, daemon=True).start()

    def _send_log(self, entry: dict, message_text: str, win, kind: str):
        """Resolve the message (blank -> sequential ``Retro N`` / ``Comment N`` default), then write
        it to the worksheet in a worker thread, driving the window with the result.

        A retro also POSTs the message-bearing comment to the robot and ticks the Retro checkbox
        (the data-capturing retro-log already fired when the window opened, see _fire_retro_log); a
        comment does neither -- it only logs the time + message.
        """
        # Time-only (like the sheet's Ctrl+Shift+: entry); USER_ENTERED lets Sheets store it as a
        # time value and the column's own format controls how it displays.
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        label = "RETRO" if kind == "retro" else "Comment"
        if message_text:
            message = message_text
        elif kind == "retro":
            self._retro_default_count += 1
            message = f"Retro {self._retro_default_count}"
        else:
            self._comment_default_count += 1
            message = f"Comment {self._comment_default_count}"

        def worker():
            try:
                if kind == "retro":
                    # The data-capturing retro-log already fired when the window opened
                    # (_fire_retro_log); here we send only the message-bearing comment.
                    RETRO_Logging.take_retro_comment(f'{entry["robot"]}.stretch', message)
                worksheet = self._open_retro_worksheet(entry)
                row, time_col, issue_col, retro_col = _locate_retro_row(worksheet.get_all_values())
                updates = [
                    {
                        "range": rowcol_to_a1(row, time_col),
                        "values": [[timestamp]]
                    },
                    {
                        "range": rowcol_to_a1(row, issue_col),
                        "values": [[message]]
                    },
                ]
                if kind == "retro":
                    updates.append({"range": rowcol_to_a1(row, retro_col), "values": [[True]]})
                worksheet.batch_update(updates, value_input_option="USER_ENTERED")
                logger.info("%s %r logged to %r row %d.", label, message, entry["worksheet_title"],
                            row)
                success = f"{label} logged: {message}"
                if kind == "retro" and getattr(win, "_capture_ok", None) is False:
                    success += "  (warning: retro data capture failed -- see log)"
                self.after(0, lambda msg=success: win.finish_success(msg))
            except Exception as e:  # noqa: BLE001 -- surfaced to the user in the window
                logger.exception("%s failed", label)
                self.after(0, lambda err=e: win.finish_failure(f"{label} failed: {err}"))

        threading.Thread(target=worker, daemon=True).start()

    def _open_retro_worksheet(self, entry: dict):
        """Reopen the stored worksheet by key + id, falling back to an id scan / title lookup."""
        spreadsheet = self.authentication.open_by_key(entry["spreadsheet_key"])
        try:
            return spreadsheet.get_worksheet_by_id(entry["worksheet_id"])
        except Exception:  # noqa: BLE001 -- older tabs / API quirks: fall back to scan + title
            for worksheet in spreadsheet.worksheets():
                if worksheet.id == entry["worksheet_id"]:
                    return worksheet
            return spreadsheet.worksheet(entry["worksheet_title"])

    # ------------------------------------------------------------------------------------------
    # Add Image: upload to the user's Drive, then insert via =IMAGE() into the next slot
    # ------------------------------------------------------------------------------------------
    @log_calls
    def open_image_window(self):
        """Open the "Add Image" picker for the currently targeted worksheet (same target the RETRO /
        Comment buttons use).

        Independent of the robot -- it only writes to the sheet.
        """
        entry = self._resolve_retro_target()
        if entry is None:
            return
        target = f'{entry.get("robot") or "—"}  ·  {entry["worksheet_title"]}'
        ImageUploadWindow(self, target_label=target,
                          on_submit=lambda win, path: self._insert_image(entry, path, win))

    def _insert_image(self, entry: dict, image_path: str, win):
        """Kick off the image insert: find the Drive "OPS Automations Screenshots" folder (creating
        it, after a confirmation, if missing), then upload + insert on a worker thread.

        Networking runs off the Tk main thread; the folder-create confirmation and all config/UI
        touches run on it. Drives the window's success / failure / cancelled states.
        """

        def find_folder():
            try:
                drive = Drive_Images.drive_service(self.authentication)
                folder_id = Drive_Images.find_screenshots_folder(drive)
            except Exception as e:  # noqa: BLE001 -- surfaced in the window
                logger.exception("Drive folder lookup failed")
                self.after(0, lambda err=e: win.finish_failure(f"Drive error: {err}"))
                return
            if folder_id is not None:
                self._upload_and_insert_image(entry, image_path, win, drive, folder_id)
            else:
                self.after(0,
                           lambda: self._confirm_and_create_folder(entry, image_path, win, drive))

        threading.Thread(target=find_folder, daemon=True).start()

    def _confirm_and_create_folder(self, entry, image_path, win, drive):
        """Main-thread: ask whether to create the Drive folder, then create it on a worker and carry
        on -- or cancel. The image window's modal grab is briefly released so the messagebox is
        interactive, then restored."""
        try:
            win.grab_release()
        except Exception:  # noqa: BLE001 -- grab may already be gone
            pass
        create = messagebox.askyesno(
            "Create Drive folder?",
            f"No “{Drive_Images.FOLDER_NAME}” folder was found in your Google Drive.\n\n"
            "Create it now to store the images inserted into sheets?")
        if win.winfo_exists():
            try:
                win.grab_set()
            except Exception:  # noqa: BLE001
                pass
        if not create:
            win.finish_cancelled("Cancelled — the image needs the Drive folder to be stored.")
            return

        def make_then_insert():
            try:
                folder_id = Drive_Images.create_screenshots_folder(drive)
            except Exception as e:  # noqa: BLE001
                logger.exception("Drive folder creation failed")
                self.after(0, lambda err=e: win.finish_failure(f"Couldn't create folder: {err}"))
                return
            self._upload_and_insert_image(entry, image_path, win, drive, folder_id)

        threading.Thread(target=make_then_insert, daemon=True).start()

    def _upload_and_insert_image(self, entry, image_path, win, drive, folder_id):
        """Worker-thread: upload + share the image, then write =IMAGE() into the next Issue
        Description slot (stamping the Time column) and size the row. Marshals the result back."""
        try:
            img_w, img_h = Drive_Images.image_dimensions(image_path)
            file_id = Drive_Images.upload_image(drive, folder_id, image_path)
            # Share to the org's domain so teammates who open the sheet can see it (best-effort --
            # it renders for the uploader either way; see Drive_Images.share_in_domain).
            shared = Drive_Images.share_in_domain(drive, file_id, Drive_Images.user_domain(drive))
            url = Drive_Images.image_url(file_id)

            worksheet = self._open_retro_worksheet(entry)
            spreadsheet = worksheet.spreadsheet
            row, time_col, issue_col, _retro_col = _locate_retro_row(worksheet.get_all_values())
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            worksheet.update([[timestamp]], rowcol_to_a1(row, time_col),
                             value_input_option="USER_ENTERED")
            Drive_Images.insert_image_in_cell(spreadsheet, worksheet, row, issue_col, url, img_w,
                                              img_h)
            logger.info("Image inserted into %r row %d (domain-shared=%s).",
                        entry["worksheet_title"], row, shared)
            self.after(0, lambda: self._image_insert_succeeded(win, entry, shared))
        except Exception as e:  # noqa: BLE001 -- surfaced in the window
            logger.exception("Image insert failed")
            self.after(0, lambda err=e: win.finish_failure(f"Image insert failed: {err}"))

    def _image_insert_succeeded(self, win, entry, shared):
        """Main-thread: report success and, the first time an image lands in a given sheet, remind
        the user about Google's one-time "Allow access" banner (which no API can grant)."""
        if shared:
            win.finish_success("Image inserted into the sheet.")
        else:
            win.finish_success("Image inserted (visible to you; couldn't share it to your "
                               "domain, so teammates may see it broken — check the log).")
        key = entry.get("spreadsheet_key")
        acked = self.config.setdefault("ImageInsertAckedSheets", [])
        if key and key not in acked:
            acked.append(key)
            self.save_config()
            ImageBannerReminderWindow(self, sheet_url=entry.get("url"))


#endregion


# --------------------------------------------------------------------------------------------------
#region RETRO placement
# --------------------------------------------------------------------------------------------------
def _retro_header_columns(row: list) -> tuple | None:
    """If `row` is the retro log's header row, return (time, issue, retro) 0-based column indexes.

    Matched case-insensitively against the header titles (see the worksheet template): the timestamp
    goes under "Time" (excluding "Time Resumed"), the message under "Issue Description", and the
    "Retro" checkbox column is ticked. Returns None unless all three titles are present in the row.
    """
    time_col = issue_col = retro_col = None
    for idx, cell in enumerate(row):
        norm = str(cell).strip().lower()
        if not norm:
            continue
        if time_col is None and norm.startswith("time") and "resume" not in norm:
            time_col = idx
        if issue_col is None and "issue description" in norm:
            issue_col = idx
        if retro_col is None and norm == "retro":
            retro_col = idx
    if None in (time_col, issue_col, retro_col):
        return None
    return time_col, issue_col, retro_col


def _locate_retro_row(grid: list) -> tuple:
    """Find where the next retro should be written in a worksheet grid (list of row lists).

    Scans for the header row (the one carrying the Time / Issue Description / Retro titles), then
    returns the first row after it whose Time *and* Issue Description cells are both blank (falling
    back to the row just past the used range if every row is filled). Returns (row, time_col,
    issue_col, retro_col), all 1-based for A1 addressing. Raises ValueError if the header row can't
    be located.
    """
    header_idx = None
    columns = None
    for i, row in enumerate(grid):
        cols = _retro_header_columns(row)
        if cols is not None:
            header_idx, columns = i, cols
            break
    if columns is None:
        raise ValueError(
            "Could not find the 'Time' / 'Issue Description' / 'Retro' header row in the worksheet."
        )

    time_col, issue_col, retro_col = columns

    def _empty(row, col):
        return not (str(row[col]).strip() if col < len(row) else "")

    target = len(grid)  # default: append on the row just past the used range
    for i in range(header_idx + 1, len(grid)):
        if _empty(grid[i], time_col) and _empty(grid[i], issue_col):
            target = i
            break
    return target + 1, time_col + 1, issue_col + 1, retro_col + 1


#endregion
