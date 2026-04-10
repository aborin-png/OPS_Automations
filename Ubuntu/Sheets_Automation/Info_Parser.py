'''
This file is responsible for parsing all the desired information out of the raw data collected from SWI.
This involves converting the string extracted from the SWI api into a python class and then extracting and linking the info
we want to the locations on google sheet.
'''
#-----------------------------------------------------------------------------------------------------------------------------

import json
import os
import pprint
from types import SimpleNamespace


import glossary as Gloss
from API_fetch import API_Fetch

#-----------------------------------------------------------------------------------------------------------------------------

def info_parser(string_data):
    '''
    This simple code is meant to turn the string of data from SWI into a python class, 
    allowing each data member to be accessed using dot notation
    '''
    return json.loads(string_data, object_hook=lambda d:SimpleNamespace(**d))


def robot_info():
    '''
    This acts as a "master" to encapsulate the other two auxiliary functions into one function. This returns an
    array of class items containing relevant information.
    '''
    data = info_parser(API_Fetch())

    return Gloss.create_new_glossary(data)