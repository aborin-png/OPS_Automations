# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Behaviour / logic for the "Sheet Editor" tab.

This is a mixin whose methods become part of the App class (see UI_Handler.py). It holds only the
tab's *functionality* -- config option lookups, dropdown/checkbox handlers, robot reachability
checks, and the sheet-generation worker. The widgets themselves are built by
``App.build_Sheet_Editor`` in UI_Handler.py, which is why every method here operates on ``self``
(the App instance) and its widget attributes.
"""
import logging
import threading

import glossary
import logger_setup
from dialogs import ProgressWindow
from logger_setup import log_calls
from Sheets_Automation import API_fetch, Sheets_editor

SUBTLE_TEXT = glossary.SUBTLE_TEXT
# Same configured "OPS" logger that UI_Handler set up via logger_setup.setup_logging().
logger = logging.getLogger(logger_setup.LOGGER_NAME)


class SheetEditorMixin:
    """Sheet Editor tab logic. Mixed into App; relies on widgets built by build_Sheet_Editor."""

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
                Sheets_editor.sheet_editor(self.authentication, sheet, self.worksheet_selection,
                                           self.test_data, self.sheet_name, self.robot_selection,
                                           progress_cb=report)
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