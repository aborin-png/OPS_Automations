'''
This file serves as an internal storage. 
This file houses any information that is meant to be hardcoded or structure definitions like classes.
'''

#-----------------------------------------------------------------------------------------------------------------------------

import datetime

#-----------------------------------------------------------------------------------------------------------------------------

'''
Zone # and the corresponding Dock/Cell name.
This will be redone with an automatic info scrapper from a premade and upto date google sheet.
'''
ZONE_NAMES = {
    203 : 'Dock 2',
    106 : 'Dock 3',
    111 : 'Dock 3',
    205 : 'Dock 4',
    206 : 'Dock 4',
    104 : 'Dock 5',
    109 : 'Dock 5',
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

CONFIG_TEMPALTE =  {
    
    
    "Options":
    {
        "Robustness":
        {   
            "Name": "Robustness",
            "Sheet": "Robustness SQA testing sheet",
            "Worksheet": 
            {
                "Cell": "CELL TEST TEMPLATE",
                "Dock": "DOCK TEST TEMPLATE"    
            },
            "Data":
            {
                "Robot"             : "data.description.nickname",
                "Serial:"           : "data.description.robotSerial",
                "SW Version"        : "data.release.releaseInfo.version",
                "Battery Firmware"  : "data.status.battery.bms1FirmwareVersion",
                "Battery % Started" : "data.status.battery.soc",
                "Dock #"            : "ZONE_NAMES[data.zoneConnectionStatus.safetydStatus.zoneId] if data.zoneConnectionStatus.zoneState else 'None'",
                "Y0 Version"        : "f'{data.status.safetyState.onRobotVersion.fwMajorVersion}.0.{data.status.safetyState.onRobotVersion.apiMajorVersion}.0'",
                "Z0 Version"        : "f'{data.status.safetyState.z0Version.fwMajorVersion}.{data.status.safetyState.z0Version.fwMinorVersion}.{data.status.safetyState.z0Version.apiMajorVersion}.0' if data.zoneConnectionStatus.zoneState else '0.0.0.0'",
                "Date:"             : "datetime.datetime.now().strftime('%m/%d/%Y')"
            }
        },

        "Performance": 
        {   
            "Name": "Performance",
            "Sheet":
            {
                "Template": "Testing Template",
                "Folder": "1Wr5w9mU5XLzIYRJHEArpZMOcSY-9ZtdQ"
                
            },
            "Worksheet": "Template",
            "Data":
            {
                "Robot"             : "data.description.nickname",
                "Serial:"           : "data.description.robotSerial",
                "SW Version"        : "data.release.releaseInfo.version",
                "Battery Firmware"  : "data.status.battery.bms1FirmwareVersion",
                "Battery % Started" : "data.status.battery.soc",
                "Dock #"            : "ZONE_NAMES[data.zoneConnectionStatus.safetydStatus.zoneId] if data.zoneConnectionStatus.zoneState else 'None'",
                "Y0 Version"        : "f'{data.status.safetyState.onRobotVersion.fwMajorVersion}.0.{data.status.safetyState.onRobotVersion.apiMajorVersion}.0'",
                "Z0 Version"        : "f'{data.status.safetyState.z0Version.fwMajorVersion}.{data.status.safetyState.z0Version.fwMinorVersion}.{data.status.safetyState.z0Version.apiMajorVersion}.0' if data.zoneConnectionStatus.zoneState else '0.0.0.0'",
                "Date:"             : "datetime.datetime.now().strftime('%m/%d/%Y')"
            }
        },

        "Endurance":
        {
            "Name": "Endurance",
            "Sheet": 
            {
                "Template": "Testing Template",
                "Folder": "1Wr5w9mU5XLzIYRJHEArpZMOcSY-9ZtdQ"

            },
            "Worksheet": "Template",
            "Data":
            {
                "Robot"             : "data.description.nickname",
                "Serial:"           : "data.description.robotSerial",
                "SW Version"        : "data.release.releaseInfo.version",
                "Battery Firmware"  : "data.status.battery.bms1FirmwareVersion",
                "Battery % Started" : "data.status.battery.soc",
                "Dock #"            : "ZONE_NAMES[data.zoneConnectionStatus.safetydStatus.zoneId] if data.zoneConnectionStatus.zoneState else 'None'",
                "Y0 Version"        : "f'{data.status.safetyState.onRobotVersion.fwMajorVersion}.0.{data.status.safetyState.onRobotVersion.apiMajorVersion}.0'",
                "Z0 Version"        : "f'{data.status.safetyState.z0Version.fwMajorVersion}.{data.status.safetyState.z0Version.fwMinorVersion}.{data.status.safetyState.z0Version.apiMajorVersion}.0' if data.zoneConnectionStatus.zoneState else '0.0.0.0'",
                "Date:"             : "datetime.datetime.now().strftime('%m/%d/%Y')"
            }
        }
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



    