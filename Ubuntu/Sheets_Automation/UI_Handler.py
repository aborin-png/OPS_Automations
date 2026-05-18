import pathlib as Path
import json
import threading
import customtkinter as ctk
import sys
from types import SimpleNamespace
from git import Repo, InvalidGitRepositoryError


import Decision_matrix 
import Sheets_editor
import API_fetch
import Info_Parser
import glossary



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
    1: ('#ffeb12', 'UNKNOWN'),
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

        self.build_main_area()
        self.build_sidebar()

        self.build_afse_monitoring()
        self.build_Sheet_Editor()

        self.after(300, lambda: threading.Thread(target=self.update_from_git, daemon=True).start())
        self.after(500, self._check_config_version)

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
#region Auxiliary Functions

    def load_config(self):
        # config_path = Decision_matrix.does_config_exist()

        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
        
    def open_settings(self):
        if not hasattr(self, "_settings_win") or not self._settings_win.winfo_exists():
            SettingsWindow(self)


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
#Auxiliary Functions
    
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

                Sheets_editor.sheet_editor(
                    self.authentication, sheet, self.worksheet_selection,
                    self.test_data, self.sheet_name, self.robot_selection,
                    progress_cb=report
                )
                completed[0] = True
            except Exception as e:
                print(f"Generate failed: {e}")
            finally:
                def _finish():
                    if progress_win.winfo_exists():
                        progress_win.after(800 if completed[0] else 0, progress_win.destroy)
                    self._generate_btn.configure(state="normal")
                self.after(0, _finish)

        threading.Thread(target=run, daemon=True).start()
        


#----------------------------------------------------------------------------------------------------------------------------------------
#Main Functions

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
#----------------------------------------------------------------------------------------------------------------------------------------
############################################################    AFSE MONITORING    ######################################################
#----------------------------------------------------------------------------------------------------------------------------------------
#region AFSE Monitoring

#----------------------------------------------------------------------------------------------------------------------------------------
#Auxiliary Functions

    def get_robot_api(self):
        robot_api = []
        robot_list = self.config['AFSE']['Robots']
        
        for robot in robot_list:
            api = API_fetch.API_Fetch(robot, ROBOT_OFFLINE)
            if api != None: 
                if robot in ROBOT_OFFLINE:
                    ROBOT_OFFLINE.remove(robot)
                data = Info_Parser.info_parser(api)
                robot_api.append([
                    data.description.nickname,
                    data.status.battery.soc,
                    data.status.lightingState.color,
                    data.status.battery.chargerMode
                    ])
            else:
                if robot not in ROBOT_OFFLINE:
                    ROBOT_OFFLINE.append(robot)
                robot_api.append([
                    robot,
                    0,
                    5,
                    5
                ])
            
        return robot_api
    
    def afse_schedule_refresh(self):
        threading.Thread(target=self.afse_refresh, daemon=True).start()

    def afse_refresh(self):
        robot_api = self.afse_fetch_data()
        self.after(0, lambda: self._afse_apply_refresh(robot_api))

    def _afse_apply_refresh(self, robot_api):
        if robot_api is not None:
            for i, (_, charge, color_code, charge_code) in enumerate(robot_api):
                if i >= len(self.afse_instances):
                    break
                status_color, status_label = STATUS_COLORS[color_code]
                charge_color, charge_status = CHARGE_STATUS[charge_code]

                self.afse_instances[i][0].configure(text=f'{charge:.0f}%')
                self.afse_instances[i][1].configure(fg_color=status_color)
                self.afse_instances[i][2].configure(text=status_label)
                self.afse_instances[i][3].configure(text= charge_status, text_color= charge_color)
        self.after(5000, self.afse_schedule_refresh)

    def afse_fetch_data(self):
        try:
            robot_api = self.get_robot_api()
        except Exception:
            robot_api = None

        return robot_api

#----------------------------------------------------------------------------------------------------------------------------------------
#Main Functions

    def build_afse_monitoring(self):
        afse_tab = self.tab_view.tab('AFSE Monitoring')
        self._afse_cards = []

        self.afse_frame = ctk.CTkScrollableFrame(afse_tab, fg_color="gray20")
        self.afse_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        for col in range(ROBOT_CARD_COLS):
            self.afse_frame.grid_columnconfigure(col, weight=1)

        # refresh_button = ctk.CTkButton(
        #     self.afse_frame,

        #     )
        
        robot_api = self.afse_fetch_data()
        
        self.afse_instances = []
        if robot_api is None:
            label = ctk.CTkLabel(self.afse_frame, text="Failed to fetch robot data.", text_color="red")
            label.grid(row=0, column=0, columnspan=ROBOT_CARD_COLS, pady=20)
            self._afse_cards.append(label)
        else:
            for i, (name, charge, color_code, charge_code) in enumerate(robot_api):
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
                status_badge.pack(pady=(0, 12), padx=12, fill="x")
                robot_status = ctk.CTkLabel(status_badge, text=status_label, text_color="white", font=ctk.CTkFont(size=12, weight="bold"))
                robot_status.pack(pady=6)

                self.afse_instances.append([robot_charge, status_badge, robot_status, robot_charge_status])


        self.afse_schedule_refresh()

    # def build_afse_refresh(self):



#endregion    


if __name__ == "__main__":
    app = App()
    app.mainloop()
