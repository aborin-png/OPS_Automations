'''
This file serves as an internal storage manager. 
Data members that are meant to be extracted out of SWI are stored and configured here along with storing dictionaries
regarding zone # and their correlating Dock/Cell.
This file also houses the Class structure that the extracted information uses. 
'''

#-----------------------------------------------------------------------------------------------------------------------------

import datetime

#-----------------------------------------------------------------------------------------------------------------------------


def get_glossary_items(data):
    '''
    This dictionary is reponsible for two taking the location in google sheets and linking it with the actualy data being extracted from SWI.
    This allows for adding data members easily.
    As an example: 
    If a new data member for the robot's Serial number needed to be added,
        1. add the name of the data as written on the google sheets doc (i.e. serial# => 'Serial:' on google sheet)
        2. create a colon between the location and the next portion
        3. Finally, add the location in the SWI api that the data can be found (refer to the manual for help on doing this)
        
        Ultimately, our addition will look like this: 
        'Serial:' : data.description.robotSerial,
    '''
    glossary_items = {
        'Robot'             : data.description.nickname,
        'Serial:'           : data.description.robotSerial,
        'SW Version'        : data.release.releaseInfo.version,
        'Battery Firmware'  : data.status.battery.bms1FirmwareVersion,
        'Battery % Started' : data.status.battery.soc,
        'Dock #'            : ZONE_NAMES[data.zoneConnectionStatus.safetydStatus.zoneId] if data.zoneConnectionStatus.zoneState else 'None',
        'Y0 Version'        : f'{data.status.safetyState.onRobotVersion.fwMajorVersion}.0.{data.status.safetyState.onRobotVersion.apiMajorVersion}.0',
        'Z0 Version'        : f'{data.status.safetyState.z0Version.fwMajorVersion}.{data.status.safetyState.z0Version.fwMinorVersion}.{data.status.safetyState.z0Version.apiMajorVersion}.0' if data.zoneConnectionStatus.zoneState else '0.0.0.0',
        'Date:'             : datetime.datetime.now().strftime('%m/%d/%Y'),
    }
    return glossary_items

#-----------------------------------------------------------------------------------------------------------------------------
#                                               DO NOT EDIT BEYOND THIS POINT
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



def create_new_glossary(api_data):
    '''
    This function is specifically for class-ifying the glossay_items dictionary so dot notation can be used
    '''
    return [Glossary(location=location, data=data) for location, data in get_glossary_items(api_data).items()]


    