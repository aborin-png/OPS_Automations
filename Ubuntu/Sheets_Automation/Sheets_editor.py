'''
This code is acting as the main file.
This code is responsible for taking the extracted data from SWI, linking it to the proper places in the 
google sheets doc, duplicating, naming, and finally editing the google sheet with the robot info.

'''

#-----------------------------------------------------------------------------------------------------------------------------

import os
import gspread
import pathlib as Path
from git import Repo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


import Info_Parser
import glossary as Gloss
import Decision_matrix as Decision
# import OPS_Automations.Ubuntu.Storage.updater as update

#-----------------------------------------------------------------------------------------------------------------------------

#region Auxiliary Functions

#This value is responsible for changing the search range the code will look for relevant data locaitons in the google sheet doc.
#(i.e. change this value to the range of cells that you want the code to automatically fill in data)
RANGE = "A1:H14"

def update_from_git():
  repo = Repo(Path.Path(__file__).parent.parent.parent)
  origin = repo.remotes.origin
  if len(origin.fetch()) > 0:
    decision_num = input('An update was found, would you like to update? (y/n): ')
    if (1 if decision_num == 'y' or decision_num == 'Y' else 0):
      origin.pull()
      print('Update Complete!')
      return True
  return False


def authenticator():
  return gspread.oauth(credentials_filename = Path.Path(__file__).parent.resolve() / 'credentials.json')

def data_linker(spreadsheet_data, robot_info):
  '''
  This code is responsible with taking the raw data extracted from the google sheet and locating where each relevant data member is located.
  After which, it will fill the immediately next cell with the relevant data that corresponds to the cell that was just found (). 
  (i.e. this code will take the data from the range specified above, locate where "SW Version" is for instance, then include the actual Software Version
  to the cell immediately to the right of it)
  '''
  updated_spreadsheet = spreadsheet_data
  for data_member in robot_info:
    found = 0
    for row in updated_spreadsheet:
      cell_count = 0
      for cell in row:
        if data_member.location == cell:
          found = 1
          if cell_count == (len(row) - 1):
            row.append(data_member.data)
          else:
            row[cell_count + 1] = data_member.data

          break
        cell_count += 1
        

      if found: break

  return updated_spreadsheet


def sheet_duplicator(sheet, worksheet, data, option_name):
  '''
  This simple code is responsible for taking in a worksheet template, duplicating it, then renaming the duplicate to properly match the test.
  '''
  return sheet.duplicate_sheet(worksheet.id, 2, new_sheet_name = f'{option_name} | {data[0].data} | {data[5].data} | {data[8].data}')
      
#endregion

#-----------------------------------------------------------------------------------------------------------------------------
#region Main Code

def main():
  '''
  This is the main code of the script.
  This code is responsible for polling the user to decide on what actions to be taken and for which sheets/worksheets to use. 
  After the user is polled, it runs all relevant functions to acquire data from SWI, link it to the deisred data, and then write
  the new information back to the desired  google sheet. 
  '''

  # if True:
  #   print(Path.Path(__file__).parent.parent.parent)
  #   return

  if update_from_git():
    print('Auto update test 7')
    return


  try:
    auth = authenticator()
    user_requests = Decision.decision_handler(auth=auth)
    
    sheet, worksheet, config_data, option_name = user_requests

    sheet = auth.open(title=sheet)
    worksheet = sheet.worksheet(worksheet)

    robot_info = Info_Parser.robot_info(config_data=config_data)
    worksheet = sheet_duplicator(sheet, worksheet, robot_info, option_name)

    values = worksheet.get(RANGE)
    if not values:
      print("No data found.")
      return

    updated_values = data_linker(values, robot_info)

    worksheet.update(updated_values, RANGE)

      
  except HttpError as err:
      print(err)
      print('Make sure that the robot is on and is not booting up.')



main()
