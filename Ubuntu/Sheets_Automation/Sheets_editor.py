'''
This code is acting as the main file.
This code is responsible for taking the extracted data from SWI, linking it to the proper places in the 
google sheets doc, duplicating, naming, and finally editing the google sheet with the robot info.

'''

#-----------------------------------------------------------------------------------------------------------------------------
#region Includes

import os
import sys
import gspread
import pathlib as Path
import webbrowser
from git import Repo
from tkinter import messagebox

from googleapiclient.errors import HttpError

from Sheets_Automation import Info_Parser
from Sheets_Automation import glossary as Gloss
from Sheets_Automation import Decision_matrix as Decision

#endregion
#-----------------------------------------------------------------------------------------------------------------------------

#region Auxiliary Functions

#This value is responsible for changing the search range the code will look for relevant data locaitons in the google sheet doc.
#(i.e. change this value to the range of cells that you want the code to automatically fill in data)
RANGE = "A1:H14"

def update_from_git():
  '''
  This code is responsible for updating the code base by checking if there is a more recent pull from github.
  This code will find the repo folder that was created when the initial repo was cloned, search if that repo
  has a more recent push to it, and finally pull that change and apply it to the current code base. 
  '''
  start_path = Path.Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path.Path(__file__).parent
  repo = Repo(start_path, search_parent_directories=True)
  origin = repo.remotes.origin
  origin.fetch()

  local_vers = repo.head.commit
  remote_vers = repo.commit('origin/' + repo.active_branch.name)

  if local_vers != remote_vers:
    decision_num = input('An update was found, would you like to update? (y/n): ')
    if decision_num.lower() == 'y':
      origin.pull()
      print('Update Complete! Please restart the program.')
      return True
  else:
    print("You're on the latest version!")
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


def worksheet_duplicator(sheet, worksheet, data, option_name):
  '''
  This simple code is responsible for taking in a worksheet template, duplicating it, then renaming the duplicate to properly match the test.
  This code is also responsible for handling duplicate worksheets and the following exceptions that the instance causes. 
  '''
  sheet_name = f'{option_name} | {data[0].data} | {data[5].data} | {data[8].data}'
  count = 1
  flag = 0
  while True:
    try:
      if count > 1 and not flag:
        if not messagebox.askyesno("Duplicate Sheet", "This sheet is a duplicate, would you like to continue?"):
          return None
        else: flag = 1

      dup_sheet = sheet.duplicate_sheet(worksheet.id, 2, new_sheet_name = sheet_name)
      return dup_sheet
    except gspread.exceptions.APIError:
      # print(err)
      sheet_name = f'{option_name} | {data[0].data} | {data[5].data} | {data[8].data} ({count})'
      count += 1
  
      
#endregion

#-----------------------------------------------------------------------------------------------------------------------------
#region Main Code

def sheet_editor(auth, sheet, worksheet, config_data, option_name, robot, progress_cb=None):
  '''
  This is the main code of the script.
  This code is responsible for polling the user to decide on what actions to be taken and for which sheets/worksheets to use.
  After the user is polled, it runs all relevant functions to acquire data from SWI, link it to the deisred data, and then write
  the new information back to the desired  google sheet.
  '''

  def report(value, message):
    if progress_cb:
      progress_cb(value, message)

  try:
    report(0.3, "Opening worksheet...")
    worksheet = sheet.worksheet(worksheet)

    report(0.5, "Fetching robot info...")
    robot_info = Info_Parser.robot_info(config_data=config_data, robot=robot)

    report(0.65, "Duplicating worksheet...")
    worksheet = worksheet_duplicator(sheet, worksheet, robot_info, option_name)
    if worksheet == None:
      return

    report(0.8, "Reading sheet data...")
    values = worksheet.get(RANGE)
    if not values:
      print("No data found.")
      return

    report(0.9, "Writing data to sheet...")
    updated_values = data_linker(values, robot_info)
    worksheet.update(updated_values, RANGE)

    report(1.0, "Complete!")
    webbrowser.open(worksheet.url)

  except HttpError as err:
      print(err)
      print('Make sure that the robot is on and is not booting up.')



# main()
