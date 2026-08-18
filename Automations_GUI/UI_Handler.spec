# -*- mode: python ; coding: utf-8 -*-
# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
#
# PyInstaller spec for the OPS Automations GUI -- a one-file build, equivalent to your old
#   pyinstaller --hidden-import=PIL._tkinter_finder --onefile --add-data "credentials.json:." UI_Handler.py
# plus the data-collection this app's dependencies actually need to launch.
#
# Written for PyInstaller 6.x. Build it FROM the Automations_GUI directory so the relative paths
# below resolve:
#
#     cd .../Automations_GUI
#     pyinstaller UI_Handler.spec
#
# Output: dist/UI_Handler  (single executable).
#
# Requirements / notes:
#   * credentials.json and assets/icon.png must exist here at build time -- they're bundled below.
#   * The `git` BINARY must be installed on the machine that RUNS the exe: GitPython shells out to
#     it. Only GitPython's Python code is bundled, not git itself.
#   * Automation_GUI_Config.json is intentionally NOT bundled: find_config() looks for it *next to
#     the exe* at runtime and writes a default there if it's missing (see UI_Handler.find_config).
#   * The window/taskbar icon is set at runtime from the bundled assets/icon.png (see
#     UI_Handler.resource_path + iconphoto). The `icon=` below only affects the exe file icon on
#     Windows/macOS; on Linux the launcher icon comes from add_favorite.py's .desktop file.

from PyInstaller.utils.hooks import collect_all, collect_submodules

# --- Data files bundled into the exe -------------------------------------------------------------
# (source_on_disk, destination_dir_inside_bundle).
datas = [
    ('credentials.json', '.'),      # gspread OAuth creds; read as <bundle>/credentials.json at runtime
    ('assets/icon.png', 'assets'),  # window/dock icon; located via resource_path("assets","icon.png")
    # Seed copy of the encrypted password store + public recipient. The app copies these out to a
    # writable, outside-git location next to the config on first run (see find_or_seed_secrets); it
    # never reads/writes them here (the bundle is a read-only temp dir). The secret key is NOT here.
    ('secrets/robot_passwords.age', 'secrets'),
    ('secrets/recipient.txt', 'secrets'),
]
binaries = []
hiddenimports = [
    'PIL._tkinter_finder',            # your existing flag: lets Pillow find Tk at runtime
    # google-auth / oauth transport bits that PyInstaller's static analysis tends to miss:
    'google.auth.transport.requests',
    'google_auth_httplib2',
    'httplib2',
    'uritemplate',
    'requests_oauthlib',
    'oauthlib',
    'oauthlib.oauth2',
    # 'testrail',                     # uncomment if you import the `testrail` package at runtime
]

# --- Packages that ship data files / compiled binaries / lazily-imported submodules --------------
# collect_all(pkg) -> (datas, binaries, hiddenimports); merge all three for each. Without
# customtkinter's bundled theme data the app won't even open a window, and pyrage is a compiled .so.
for pkg in (
    'customtkinter',        # theme JSONs + widget image assets (REQUIRED to start)
    'pyrage',               # compiled Rust age bindings (.so) -- robot-password decryption
    'cv2',                  # OpenCV binaries (also has a built-in hook; kept for safety)
    'gspread',
    'google.auth',
    'google.oauth2',
    'google_auth_oauthlib',  # gspread.oauth() login flow
    'googleapiclient',       # googleapiclient.errors.HttpError + discovery data
    'git',                   # GitPython (Python side only -- see the git-binary note above)
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += collect_submodules('bs4')  # BeautifulSoup parser backends

a = Analysis(
    ['UI_Handler.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='UI_Handler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,              # keep True while iterating so tracebacks show; set False to hide it
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.png',    # exe-file icon on Windows/macOS; no-op on Linux (uses the .desktop)
)