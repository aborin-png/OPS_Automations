'''
This file is responsible for any user facing interaction.
This means that this file is meant to poll the user for the proper actions to be taken and for choosing which
files these actions should done on.
The code will then return a list of all decisions the user had made. 
'''

#-----------------------------------------------------------------------------------------------------------------------------
#region Includes

import datetime
import sys
import gspread
import json
import pathlib as Path

from googleapiclient.discovery import build

from Info_Parser import get_config
from glossary import CONFIG_TEMPALTE

#endregion
#-----------------------------------------------------------------------------------------------------------------------------
#region Auxiliary Functions

def multiple_sheets_response(Folder, auth):
    '''
    This function is designed for options that have multiple different google sheet options that are not statically named.
    For instance, the SQA sheets that are used change depending on which generation of robot is being tested. This means that
    there are multiple differently named sheets inside a common directory in google drive.
    This function would then search through that common directory and list all google sheets in that directory and allow the 
    user to choose which sheet they would like to use.  
    '''

    sheet_files = auth.list_spreadsheet_files(folder_id = Folder)
    option_list = []

    for count, file in enumerate(sheet_files):
        print(f'{count + 1}: {file['name']}')
        option_list.append(file)

    while True:
            user_in = int(input('Please select which Google Sheet you would like to use: ')) - 1
            
            if user_in + 1 <= len(option_list):
                sheet = option_list[user_in]['name']
                break 
            else:
                print('This is not a valid option.')

    return sheet

def does_config_exist():
    '''
    This code is used for checking of a config file exists and, if one does not exist, creates a 
    default one that can be edited. 
    The correct location for the config file is outside of the OPS_Automations folder when the repo
    is first cloned from github.
    '''
    print('Checking if Config.json exists...')
    if getattr(sys, 'frozen', False):
        path_outside_repo = Path.Path(sys.executable).parent.parent.parent.parent / 'Config.json'
    else:
        path_outside_repo = Path.Path(__file__).parent.parent.parent.parent / 'Config.json'
        
    if path_outside_repo.exists():
        print('Config.json found!')
    else:
        print(f'No Config.json file detected, creating a default at: {path_outside_repo}')
        with open(path_outside_repo, 'w') as config:
            json.dump(CONFIG_TEMPALTE, config, indent=4)

    return path_outside_repo

#endregion
#-----------------------------------------------------------------------------------------------------------------------------
#region Decision Handler

def decision_handler(auth):
    '''
    This function is main handler for all user faced interactions. 
    It is responsible for polling the user for any and all configurable choices to be made (i.e. which sheet to use and which
    worksheets (if multiple are present) to use in the selected sheet)
    The code will also link the dataset to be extracted from SWI depending on the which sheet is selected. 
    '''

    path_to_config = does_config_exist()
    config_options = get_config(path_to_config).Options
    option_list = []
    count = 0
    
    for option, data in vars(config_options).items():
        option_list.append([option, data])
        print(f'{count+1}: {option}')
        count += 1

    selected_option = option_list[int(input('Please select which test type you would like to run: ')) - 1][1]
    sheet = selected_option.Sheet


    if hasattr(sheet, 'Template'):
        response = input(f'A template Sheet is present ("{sheet.Template.Name}"), would you like to create a new Google sheet? (y/n): ')

        if response.lower() == 'y':

            drive = build('drive', 'v3', credentials = auth.http_client.auth)

            new_sheet = drive.files().copy(fileId= sheet.Template.Key, body = {'name': input("What would you like to name the new Google Sheet: ")}, supportsAllDrives=True).execute()
            sheet = auth.open_by_key(new_sheet['id'])
        else:
            sheet = auth.open(title=multiple_sheets_response(sheet.Folder, auth))
    else:
        sheet = auth.open(title=sheet)


    if selected_option.Sheet == 'Robustness SQA testing sheet':
        worksheet_options = config_options.Robustness.Worksheet
        robustness_list = []

        for count, data in enumerate(vars(worksheet_options).items()):
            robustness_list.append(data[1])
            print(f'{count + 1}: {data[1]}')
            
        while True:
            
            user_in = int(input('Please select which worksheet template to use: ')) - 1
            
            if user_in + 1 <= len(robustness_list):
                worksheet = robustness_list[user_in]
                break 
            else:
                print('This is not a valid option.')
    
    else:
        worksheet = selected_option.Worksheet

    data = selected_option.Data
    option_name = selected_option.Name
    

    return [sheet, worksheet, data, option_name]
