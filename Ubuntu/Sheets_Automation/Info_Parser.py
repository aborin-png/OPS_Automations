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
from functools import reduce
import datetime


import glossary as Gloss
from API_fetch import API_Fetch

ZONE_NAMES = Gloss.ZONE_NAMES
#-----------------------------------------------------------------------------------------------------------------------------

def info_parser(string_data):
    '''
    This simple code is meant to turn the string of data from SWI into a python class, 
    allowing each data member to be accessed using dot notation
    '''
    return json.loads(string_data, object_hook=lambda d:SimpleNamespace(**d))

def get_config(config_path):
    with open(config_path, 'r') as file:
        file = file.read()
        return json.loads(file, object_hook=lambda d:SimpleNamespace(**d))
    
def config_recontruction(dict_to_reconstruct, data):
    '''
    This function is responsible for reconstructing the data extracted from the config file into usuable code that python can interpret
    and itemize into a class structure.
    '''
    
    return [Gloss.Glossary(location=location, data = eval(data_member)) for location, data_member in vars(dict_to_reconstruct).items()]


    


def robot_info(config_data):
    '''
    This acts as a "master" to encapsulate the other two auxiliary functions into one function. This returns an
    array of class items containing relevant information.
    '''
    data = info_parser(API_Fetch())


    return config_recontruction(config_data, data=data)
