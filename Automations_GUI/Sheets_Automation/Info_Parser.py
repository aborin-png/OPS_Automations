# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""This file is responsible for parsing all the desired information out of the raw data collected
from SWI.

This involves converting the string extracted from the SWI api into a python class and then
extracting and linking the info we want to the locations on google sheet.
"""
#-----------------------------------------------------------------------------------------------------------------------------

import json
from functools import reduce
from types import SimpleNamespace

import glossary as Gloss
from Sheets_Automation.API_fetch import API_Fetch

ZONE_NAMES = Gloss.ZONE_NAMES
#-----------------------------------------------------------------------------------------------------------------------------


def info_parser(string_data):
    """Turn the raw robot-info payload from SWI into a RobotInfo object.

    All knowledge of the API's nested shape lives in RobotInfo.from_api; callers just read the flat,
    documented attributes off the returned object.
    """
    return Gloss.RobotInfo.from_api(string_data)


def config_recontruction(data_map, robot_data):
    """Pair each sheet column label in the config's "Data" block with the corresponding value from a
    RobotInfo instance.

    The config maps a column label (e.g. "SW Version") to a RobotInfo attribute / property name
    (e.g. "sw_version"); this looks each one up with getattr -- no eval -- and returns the
    Glossary(location, data) list (in config order) that Sheets_editor consumes positionally.
    """
    items = data_map.items() if isinstance(data_map, dict) else vars(data_map).items()
    return [
        Gloss.Glossary(location=location, data=getattr(robot_data, attr_name))
        for location, attr_name in items
    ]


def robot_info(config_data, robot):
    """This acts as a "master" to encapsulate the other two auxiliary functions into one function.

    This returns an array of class items containing relevant information.
    """
    data = info_parser(API_Fetch(robot=robot, robot_offline=[]))

    return config_recontruction(config_data, robot_data=data)
