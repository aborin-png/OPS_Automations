import pathlib
import json
import customtkinter as ctk
import sys
from types import SimpleNamespace

sys.path.append('Ubuntu/Sheets_Automation')

# from OPS_Automations.Ubuntu.Sheets_Automation.Decision_matrix import does_config_exist
import Decision_matrix 
import Sheets_editor



ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CONFIG_PATH = pathlib.Path(sys.executable).parent.parent.parent.parent / 'Config.json'

TAB_COLORS = {
    "Sheet Editor": "#5B9BD5",
    "Test Rails":   "#70AD47",
    "Fault Logging": "#ED7D31",
}


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("400x300")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(self, text="Settings", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        ctk.CTkLabel(self, text="No settings configured yet.", text_color="gray").pack(pady=10)
        ctk.CTkButton(self, text="Close", command=self.destroy).pack(pady=20)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # self.

        self.title("OPS Automations")
        self.geometry("900x600")
        self.minsize(700, 450)

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)

        self._config = self.load_config()
        self.authentication = Sheets_editor.authenticator()

        self.build_main_area()
        self.build_sidebar()

        self.build_Sheet_Editor()

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
        config_path = Decision_matrix.does_config_exist()

        with open(config_path, "r") as f:
            return json.load(f)
        
    def open_settings(self):
        if not hasattr(self, "_settings_win") or not self._settings_win.winfo_exists():
            self._settings_win = SettingsWindow(self)
        self._settings_win.focus()

    
#endregion
#----------------------------------------------------------------------------------------------------------------------------------------
############################################################    SHEETS EDITOR    ########################################################
#----------------------------------------------------------------------------------------------------------------------------------------
#region Sheets Editor

#----------------------------------------------------------------------------------------------------------------------------------------
#Auxiliary Functions
    
    def get_config_option(self, test_name: str):
        self.selected_option = self._config.get('Options', {}).get(test_name, {})

    def has_template(self, test_name: str) -> bool:
        option = self._config.get("Options", {}).get(test_name, {})
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

        

    def on_test_type_changed(self, _: str):

        test_type = self._test_type_var.get()
        if self.has_template(test_name=test_type):
            self._template_checkbox.grid()
        else:
            self._template_checkbox.grid_remove()

        
        self.sheet_options = self.get_sheet_options(test_type=test_type)[0]
        self._sheet_type_var.set(self.sheet_options[0] if self.sheet_options else "")
        self._sheet_type_menu.configure(values=self.sheet_options)
        
        self.test_data = self.selected_option['Data']
        


    def on_template_checked(self):
        if self._use_template_var.get():
            self._sheet_type_menu.configure(state= 'disabled')
            self.sheet_selection = self.selected_option['Sheet']['Template']
        else:
            self._sheet_type_menu.configure(state= 'enabled')
            self.sheet_selection = self._sheet_type_var.get()

    def on_sheet_selection(self, _:str):
        self.sheet_selection = self._sheet_type_var.get()
        print(self.sheet_selection)


#----------------------------------------------------------------------------------------------------------------------------------------
#Main Functions

    def build_Sheet_Editor(self):
        sheet_tab = self.tab_view.tab("Sheet Editor")
        options = list(self._config.get("Options", {}).keys())

        self.sheet_frame = ctk.CTkFrame(sheet_tab, fg_color="gray20")
        self.sheet_frame.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkLabel(self.sheet_frame, text="Test Type:").grid(
            row=0, column=0, padx=(12, 8), pady=12, sticky="w"
        )

        self._test_type_var = ctk.StringVar(value=options[0] if options else "")
        self._test_type_menu = ctk.CTkOptionMenu(
            self.sheet_frame,
            values=options,
            variable=self._test_type_var,
            command=self.on_test_type_changed,
        )
        self._test_type_menu.grid(row=0, column=1, padx=(0, 12), pady=12, sticky="w")

    
        sheet_options = self.get_sheet_options(test_type=self._test_type_var.get())[0]
        self._sheet_type_var = ctk.StringVar(value=sheet_options[0] if sheet_options else "")
        self._sheet_type_menu = ctk.CTkOptionMenu(
            self.sheet_frame,
            values=sheet_options,
            variable=self._sheet_type_var,
            command= self.on_sheet_selection
        )
        self._sheet_type_menu.grid(row=2, column=1, columnspan=2, padx=12, pady=(0, 12), sticky="w")


        self._use_template_var = ctk.BooleanVar(value=False)
        self._template_checkbox = ctk.CTkCheckBox(
            self.sheet_frame,
            text="Use Template Worksheet",
            variable=self._use_template_var,
        )
        self._template_checkbox.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="w")
        self._template_checkbox.grid_remove()

        # self.update_template_visibility()

    
#----------------------------------------------------------------------------------------------------------------------------------------
#region Main

if __name__ == "__main__":
    app = App()
    app.mainloop()
