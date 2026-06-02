'''
This file serves as an internal storage. 
This file houses any information that is meant to be hardcoded or structure definitions like classes.
'''

#-----------------------------------------------------------------------------------------------------------------------------

import datetime

#-----------------------------------------------------------------------------------------------------------------------------

'''
The "global truth" google sheet (STO: Test Cells, Docks, Conveyors, Safety Systems) that
the GUI scans on startup to build ZONE_NAMES / ZONE_TYPES dynamically. See Sheets_Automation/Zone_scanner.py.
'''
STO_SHEET_KEY = "1YQfsfgoX5kXGT3irN0pk-wZOee5WpiXICXXe4N6qRRQ"
STO_SHEET_GID = 1613910811

'''
Zone # and the corresponding Dock/Cell name.
These values are a hardcoded FALLBACK only. On startup the GUI scans the STO sheet above and
overwrites ZONE_NAMES / ZONE_TYPES in place with the live data; this map is only used if that scan fails.
'''
ZONE_NAMES = {
    203 : 'Dock 2',
    106 : 'Dock 3',
    111 : 'Dock 3',
    205 : 'Dock 4',
    206 : 'Dock 4',
    214 : 'Dock 5',
    200 : 'Dock 6',
    207 : 'Dock 6',
    201 : 'Dock 7',
    208 : 'Dock 7',
    202 : 'Dock 8',
    209 : 'Dock 8',
    213 : 'Dock 9',
    211 : 'Dock 10',
    108 : 'Dock 12',
    110 : 'Dock 13',
    35  : 'Cell 0',
    32  : 'Cell 1',
    40  : 'Cell 2',
    37  : 'Cell 3',
    46  : 'Cell 4',
    31  : 'Cell 4',
    47  : 'Cell 5',
    44  : 'Cell 5',
    57  : 'Cell 6',
    50  : 'Cell 7',
    36  : 'Cell 0 (POST)',
    62  : 'Cell 0 (POST)'
}

'''
Zone ID -> 'Dock' or 'Cell'. Used to pick which Reolink camera IP to stream from
(docks and cells live on separate NVRs / IPs). A zone is a 'Dock' if its name starts with
"Dock", otherwise it is treated as a 'Cell'. Like ZONE_NAMES, this is a fallback that gets
overwritten in place by the startup sheet scan.
'''
ZONE_TYPES = {
    zone_id: ('Dock' if name.lower().startswith('dock') else 'Cell')
    for zone_id, name in ZONE_NAMES.items()
}

CAMERA_CHANNELS = {               # robot Zone ID -> 1-based NVR channel number
    203 : 1,
    106 : 9,
    111 : 9,
    205 : 7,
    206 : 7,
    214 : 2,
    200 : 10,
    207 : 10,
    201 : 11,
    208 : 11,
    202 : 5,
    209 : 5,
    213 : 6,
    211 : 4,
    108 : 1,
    110 : 3,
    35  : 9,
    32  : 10,
    40  : 6,
    37  : 8,
    46  : 1,
    31  : 1,
    47  : 3,
    44  : 3,
    57  : 5,
    50  : 4,
    36  : 9,
    62  : 9
    }

CONFIG_VERSION = "1.2.0"

CONFIG_TEMPALTE =  {
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
                "Robot": "data.description.nickname",
                "Serial:": "data.description.robotSerial",
                "SW Version": "data.release.releaseInfo.version",
                "Battery Firmware": "data.status.battery.bms1FirmwareVersion",
                "Battery % Started": "data.status.battery.soc",
                "Dock #": "ZONE_NAMES[data.zoneConnectionStatus.safetydStatus.zoneId] if data.zoneConnectionStatus.zoneState else 'None'",
                "Y0 Version": "f'{data.status.safetyState.onRobotVersion.fwMajorVersion}.0.{data.status.safetyState.onRobotVersion.apiMajorVersion}.0'",
                "Z0 Version": "f'{data.status.safetyState.z0Version.fwMajorVersion}.{data.status.safetyState.z0Version.fwMinorVersion}.{data.status.safetyState.z0Version.apiMajorVersion}.0' if data.zoneConnectionStatus.zoneState else '0.0.0.0'",
                "Date:": "datetime.datetime.now().strftime('%m/%d/%Y')"
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
                "Robot": "data.description.nickname",
                "Serial:": "data.description.robotSerial",
                "SW Version": "data.release.releaseInfo.version",
                "Battery Firmware": "data.status.battery.bms1FirmwareVersion",
                "Battery % Started": "data.status.battery.soc",
                "Dock #": "ZONE_NAMES[data.zoneConnectionStatus.safetydStatus.zoneId] if data.zoneConnectionStatus.zoneState else 'None'",
                "Y0 Version": "f'{data.status.safetyState.onRobotVersion.fwMajorVersion}.0.{data.status.safetyState.onRobotVersion.apiMajorVersion}.0'",
                "Z0 Version": "f'{data.status.safetyState.z0Version.fwMajorVersion}.{data.status.safetyState.z0Version.fwMinorVersion}.{data.status.safetyState.z0Version.apiMajorVersion}.0' if data.zoneConnectionStatus.zoneState else '0.0.0.0'",
                "Date:": "datetime.datetime.now().strftime('%m/%d/%Y')"
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
                "Robot": "data.description.nickname",
                "Serial:": "data.description.robotSerial",
                "SW Version": "data.release.releaseInfo.version",
                "Battery Firmware": "data.status.battery.bms1FirmwareVersion",
                "Battery % Started": "data.status.battery.soc",
                "Dock #": "ZONE_NAMES[data.zoneConnectionStatus.safetydStatus.zoneId] if data.zoneConnectionStatus.zoneState else 'None'",
                "Y0 Version": "f'{data.status.safetyState.onRobotVersion.fwMajorVersion}.0.{data.status.safetyState.onRobotVersion.apiMajorVersion}.0'",
                "Z0 Version": "f'{data.status.safetyState.z0Version.fwMajorVersion}.{data.status.safetyState.z0Version.fwMinorVersion}.{data.status.safetyState.z0Version.apiMajorVersion}.0' if data.zoneConnectionStatus.zoneState else '0.0.0.0'",
                "Date:": "datetime.datetime.now().strftime('%m/%d/%Y')"
            }
        }
    },
    "AFSE": {
        "Robots": [
            "sb20",
            "sb12",
            "sb24",
            "sb13",
            "sb16",
            "sb25",
            "sb17",
            "sb18"

        ]
    },
    "UI": {
        "Scaling": 1.0
    }
}

'''
This is the class structure that the data extracted from SWI follows,
Additional functions can be added but the only part that is fully utilized is it the init function.
'''
class Glossary: 
    def __init__(self, location, data):
        self.location = location
        self.data = data
    
    def new_location(self, location):
        self.location = location
    
    def new_data(self, data):
        self.data = data



    