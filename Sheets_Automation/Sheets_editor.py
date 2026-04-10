'''
This code is acting as the main file.
This code is responsible for taking the extracted data from SWI, linking it to the proper places in the 
google sheets doc, duplicating, naming, and finally editing the google sheet with the robot info.

'''

#-----------------------------------------------------------------------------------------------------------------------------

import os.path
import gspread

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import Info_Parser
import glossary as Gloss

#-----------------------------------------------------------------------------------------------------------------------------

#region Auxiliary Functions

#This value is responsible for changing the search range the code will look for relevant data locaitons in the google sheet doc.
#(i.e. change this value to the range of cells that you want the code to automatically fill in data)
RANGE = "A1:H14"


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


def sheet_duplicator(sheet, worksheet, data):
  '''
  This simple code is responsible for taking in a worksheet template, duplicating it, then renaming the duplicate to properly match the test.
  '''
  #TODO: Add compatability for different forms of testing (i.e. Endurance Testing/Performance Runs) 

  return sheet.duplicate_sheet(worksheet.id, 2, new_sheet_name = f'MR | {data[0].data} | {data[4].data} | {data[6].data}')
      
#endregion

#-----------------------------------------------------------------------------------------------------------------------------
#region Main Code

def main():
  '''
  This is the main code of the script.
  This code is responsible for acquiring the sheet we are working with (dependent on the test to be run), acquiring the template to duplicate and name,
  then linking the data to the appropriate locations and writing all data back to the worksheet. 
  '''

  #TODO: Add compatability for different google Sheets (maybe work on a gui that allows additions of new sheets)

  try:

    sheet = gspread.oauth(credentials_filename='credentials.json').open(title="Robustness SQA testing sheet")
    

    while True:
      which_worksheet = int(input("Is this a Dock or Cell Robustness Test?\n1: Dock Testing\n2: Cell Testing\n"))
      if which_worksheet == 1:
        worksheet = sheet.worksheet('DOCK TEST TEMPLATE')
        break
      elif which_worksheet == 2:
        worksheet = sheet.worksheet('CELL TEST TEMPLATE')
        break
      else:
        print("That is not a valid option")
    

    robot_info = Info_Parser.robot_info()
    worksheet = sheet_duplicator(sheet, worksheet, robot_info)

    values = worksheet.get(RANGE)
    if not values:
      print("No data found.")
      return

    updated_values = data_linker(values, robot_info)

    worksheet.update(updated_values, RANGE)

      
  except HttpError as err:
      print(err)
      print('Make sure that the robot is on and is not booting up.')


if __name__ == "__main__":
  main()
