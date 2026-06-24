# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""This file serves as an internal storage.

This file houses any information that is meant to be hardcoded or structure definitions like
classes.
"""

#-----------------------------------------------------------------------------------------------------------------------------

import datetime
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

#-----------------------------------------------------------------------------------------------------------------------------
'''
The "global truth" google sheet (STO: Test Cells, Docks, Conveyors, Safety Systems) that
the GUI scans on startup to build ZONE_NAMES / ZONE_TYPES dynamically. See Sheets_Automation/Zone_scanner.py.
'''
STO_SHEET_KEY = "1YQfsfgoX5kXGT3irN0pk-wZOee5WpiXICXXe4N6qRRQ"
STO_SHEET_GID = 1613910811
"""This value is responsible for changing the search range the code will look for relevant data in
the google sheet doc.

(i.e. change this value to the range of cells that you want the code to automatically read and fill
in data with)
"""
GOOGLE_SHEET_RANGE = "A1:H14"
"""Zone # and the corresponding Dock/Cell name.

These values are a hardcoded FALLBACK only. On startup the GUI scans the STO sheet above and
overwrites ZONE_NAMES / ZONE_TYPES in place with the live data; this map is only used if that scan
fails.
"""
ZONE_NAMES = {
    203: 'Dock 2',
    106: 'Dock 3',
    111: 'Dock 3',
    205: 'Dock 4',
    206: 'Dock 4',
    214: 'Dock 5',
    200: 'Dock 6',
    207: 'Dock 6',
    201: 'Dock 7',
    208: 'Dock 7',
    202: 'Dock 8',
    209: 'Dock 8',
    213: 'Dock 9',
    211: 'Dock 10',
    108: 'Dock 12',
    110: 'Dock 13',
    35: 'Cell 0',
    32: 'Cell 1',
    40: 'Cell 2',
    37: 'Cell 3',
    46: 'Cell 4',
    31: 'Cell 4',
    47: 'Cell 5',
    44: 'Cell 5',
    57: 'Cell 6',
    50: 'Cell 7',
    36: 'Cell 0 (POST)',
    62: 'Cell 0 (POST)'
}
"""Zone ID -> 'Dock' or 'Cell'.

Used to pick which Reolink camera IP to stream from (docks and cells live on separate NVRs / IPs). A
zone is a 'Dock' if its name starts with "Dock", otherwise it is treated as a 'Cell'. Like
ZONE_NAMES, this is a fallback that gets overwritten in place by the startup sheet scan.
"""
ZONE_TYPES = {
    zone_id: ('Dock' if name.lower().startswith('dock') else 'Cell')
    for zone_id, name in ZONE_NAMES.items()
}

CAMERA_CHANNELS = {  # robot Zone ID -> 1-based NVR channel number
    203: 1,
    106: 9,
    111: 9,
    205: 7,
    206: 7,
    214: 2,
    200: 10,
    207: 10,
    201: 11,
    208: 11,
    202: 5,
    209: 5,
    213: 6,
    211: 4,
    108: 1,
    110: 3,
    35: 9,
    32: 10,
    40: 6,
    37: 8,
    46: 1,
    31: 1,
    47: 3,
    44: 3,
    57: 5,
    50: 4,
    36: 9,
    62: 9
}

ROBOT_BEHAVIORS = {
    "AFSE": "60005",
    "STOW": "40",
}

CONFIG_VERSION = "1.3.0"

CONFIG_TEMPLATE = {
    "Version": CONFIG_VERSION,
    "Options": {
        "Robustness": {
            "Name": "Robustness",
            "Sheet": "Robustness SQA testing sheet",
            "Worksheet": {
                "Cell": "CELL TEST TEMPLATE",
                "Dock": "DOCK TEST TEMPLATE"
            },
            "Data": {
                "Robot": "nickname",
                "Serial:": "robot_serial",
                "SW Version": "sw_version",
                "Battery Firmware": "battery_firmware",
                "Battery % Started": "soc",
                "Dock #": "dock_name",
                "Y0 Version": "y0_version",
                "Z0 Version": "z0_version",
                "Date:": "date"
            }
        },
        "Performance": {
            "Name": "Performance",
            "Sheet": {
                "Template": {
                    "Name": "Testing Template",
                    "Key": "1G2Zsxxu4F5Au7WyIFWe4A0m4umpXo8BmgL70VSy3Q-s"
                },
                "Folder": "1Wr5w9mU5XLzIYRJHEArpZMOcSY-9ZtdQ"
            },
            "Worksheet": "Template",
            "Data": {
                "Robot": "nickname",
                "Serial:": "robot_serial",
                "SW Version": "sw_version",
                "Battery Firmware": "battery_firmware",
                "Battery % Started": "soc",
                "Dock #": "dock_name",
                "Y0 Version": "y0_version",
                "Z0 Version": "z0_version",
                "Date:": "date"
            }
        },
        "Endurance": {
            "Name": "Endurance",
            "Sheet": {
                "Template": {
                    "Name": "Testing Template",
                    "Key": "1G2Zsxxu4F5Au7WyIFWe4A0m4umpXo8BmgL70VSy3Q-s"
                },
                "Folder": "1Wr5w9mU5XLzIYRJHEArpZMOcSY-9ZtdQ"
            },
            "Worksheet": "Template",
            "Data": {
                "Robot": "nickname",
                "Serial:": "robot_serial",
                "SW Version": "sw_version",
                "Battery Firmware": "battery_firmware",
                "Battery % Started": "soc",
                "Dock #": "dock_name",
                "Y0 Version": "y0_version",
                "Z0 Version": "z0_version",
                "Date:": "date"
            }
        }
    },
    "AFSE": {
        "Robots": ["sb20", "sb12", "sb24", "sb13", "sb16", "sb25", "sb17", "sb18"]
    },
    "UI": {
        "Scaling": 1.0
    }
}
"""This is the class structure that the data extracted from SWI follows, Additional functions can be
added but the only part that is fully utilized is it the init function."""


class Glossary:

    def __init__(self, location, data):
        self.location = location
        self.data = data

    def new_location(self, location):
        self.location = location

    def new_data(self, data):
        self.data = data


#-----------------------------------------------------------------------------------------------------------------------------
#region RobotInfo


@dataclass
class RobotInfo:
    """Every data member extracted from the robot's /api/info/robot-info endpoint, in one place.

    Build instances with ``RobotInfo.from_api(raw_json_string)`` -- ``from_api`` is the ONLY code
    that knows the nested shape of the API payload, so when the API changes there is a single place
    to update. Each field's comment gives its original API path so the mapping is auditable at a
    glance. Fields default to the same values the AFSE view treats as "offline", so a malformed or
    unreachable robot degrades gracefully instead of raising.

    The ``Data`` blocks in CONFIG_TEMPLATE map a sheet column label to one of the attribute /
    property names below (see Sheets_Automation/Info_Parser.config_recontruction).
    """
    # --- description ---
    nickname: str = ""                 # description.nickname
    robot_serial: str = ""             # description.robotSerial  (shown on sheets)
    serial: str = ""                   # description.serial       (robot password lookup)

    # --- release.releaseInfo ---
    sw_version: str = ""               # release.releaseInfo.version

    # --- status.battery ---
    battery_firmware: str = ""         # status.battery.bms1FirmwareVersion
    soc: float = 0.0                   # status.battery.soc
    charger_mode: int = 5              # status.battery.chargerMode    (5 == OFFLINE fallback)

    # --- status.lightingState ---
    lighting_color: int = 5            # status.lightingState.color    (5 == OFFLINE fallback)

    # --- zoneConnectionStatus ---
    zone_connected: bool = False       # zoneConnectionStatus.zoneState
    zone_id: Optional[int] = None      # zoneConnectionStatus.safetydStatus.zoneId

    # --- status.safetyState ---
    y0_fw_major: int = 0               # status.safetyState.onRobotVersion.fwMajorVersion
    y0_api_major: int = 0              # status.safetyState.onRobotVersion.apiMajorVersion
    z0_fw_major: int = 0               # status.safetyState.z0Version.fwMajorVersion
    z0_fw_minor: int = 0               # status.safetyState.z0Version.fwMinorVersion
    z0_api_major: int = 0              # status.safetyState.z0Version.apiMajorVersion

    #---- Derived values (previously computed inline by the CONFIG_TEMPLATE eval strings) ----

    @property
    def y0_version(self) -> str:
        return f"{self.y0_fw_major}.0.{self.y0_api_major}.0"

    @property
    def z0_version(self) -> str:
        if not self.zone_connected:
            return "0.0.0.0"
        return f"{self.z0_fw_major}.{self.z0_fw_minor}.{self.z0_api_major}.0"

    @property
    def date(self) -> str:
        return datetime.datetime.now().strftime("%m/%d/%Y")

    @property
    def dock_name(self) -> str:
        """Dock/cell name for the connected zone, or 'None'.

        Reads the module-level ZONE_NAMES, which the GUI overwrites in place on startup with live
        STO-sheet data (see UI_Handler.load_zone_data), so this always reflects current zones.
        """
        if self.zone_connected and self.zone_id is not None:
            return ZONE_NAMES.get(self.zone_id, "None")
        return "None"

    @property
    def connected_zone_id(self):
        """Zone id when connected, else the string 'None' -- the convention the AFSE view uses as a
        ZONE_NAMES / CAMERA_CHANNELS lookup key."""
        if self.zone_connected and self.zone_id is not None:
            return self.zone_id
        return "None"

    #---- Construction ----

    @classmethod
    def from_api(cls, raw: str) -> "RobotInfo":
        """Parse a raw robot-info payload (the string returned by API_fetch.API_Fetch) into a
        RobotInfo. This is the single source of truth for the API's nested field paths."""
        data = json.loads(raw, object_hook=lambda d: SimpleNamespace(**d))
        dig = cls._dig
        return cls(
            nickname=dig(data, "description.nickname", ""),
            robot_serial=dig(data, "description.robotSerial", ""),
            serial=dig(data, "description.serial", ""),
            sw_version=dig(data, "release.releaseInfo.version", ""),
            battery_firmware=dig(data, "status.battery.bms1FirmwareVersion", ""),
            soc=dig(data, "status.battery.soc", 0.0),
            charger_mode=dig(data, "status.battery.chargerMode", 5),
            lighting_color=dig(data, "status.lightingState.color", 5),
            zone_connected=bool(dig(data, "zoneConnectionStatus.zoneState", False)),
            zone_id=dig(data, "zoneConnectionStatus.safetydStatus.zoneId"),
            y0_fw_major=dig(data, "status.safetyState.onRobotVersion.fwMajorVersion", 0),
            y0_api_major=dig(data, "status.safetyState.onRobotVersion.apiMajorVersion", 0),
            z0_fw_major=dig(data, "status.safetyState.z0Version.fwMajorVersion", 0),
            z0_fw_minor=dig(data, "status.safetyState.z0Version.fwMinorVersion", 0),
            z0_api_major=dig(data, "status.safetyState.z0Version.apiMajorVersion", 0),
        )

    @staticmethod
    def _dig(obj, path, default=None):
        """Walk a dotted attribute path safely, returning ``default`` if any hop is missing.

        A robot can, for example, report zoneState=True while safetydStatus is missing the zoneId
        field, so every hop is guarded rather than assumed.
        """
        for attr in path.split("."):
            obj = getattr(obj, attr, None)
            if obj is None:
                return default
        return obj


#endregion
