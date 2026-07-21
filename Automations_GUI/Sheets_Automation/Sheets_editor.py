# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""This code is acting as the main file.

This code is responsible for taking the extracted data from SWI, linking it to the proper places in
the google sheets doc, duplicating, naming, and finally editing the google sheet with the robot
info.
"""

#-----------------------------------------------------------------------------------------------------------------------------
#region Includes

import logging
import os
import pathlib as Path
import sys
import webbrowser
from tkinter import messagebox

import glossary as Gloss

logger = logging.getLogger("OPS.sheets_editor")
import gspread
from git import Repo
from googleapiclient.errors import HttpError
from Sheets_Automation import Info_Parser

#endregion
#-----------------------------------------------------------------------------------------------------------------------------

#region Auxiliary Functions


def authenticator():
    return gspread.oauth(credentials_filename=Path.Path(__file__).parent.parent.resolve() /
                         'credentials.json')


def data_linker(spreadsheet_data, robot_info):
    """This code is responsible with taking the raw data extracted from the google sheet and
    locating where each relevant data member is located.

    After which, it will fill the immediately next cell with the relevant data that corresponds to
    the cell that was just found (). (i.e. this code will take the data from the range specified
    above, locate where "SW Version" is for instance, then include the actual Software Version to
    the cell immediately to the right of it)
    """
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

            if found:
                break

    return updated_spreadsheet


def worksheet_duplicator(sheet, worksheet, data, option_name):
    """This simple code is responsible for taking in a worksheet template, duplicating it, then
    renaming the duplicate to properly match the test.

    This code is also responsible for handling duplicate worksheets and the following exceptions
    that the instance causes.
    """
    sheet_name = f'{option_name} | {data[0].data} | {data[5].data} | {data[8].data}'
    count = 1
    flag = 0
    while True:
        try:
            if count > 1 and not flag:
                if not messagebox.askyesno(
                        "Duplicate Sheet",
                        "This sheet is a duplicate, would you like to continue?"):
                    return None
                else:
                    flag = 1

            dup_sheet = sheet.duplicate_sheet(worksheet.id, 3, new_sheet_name=sheet_name)
            return dup_sheet
        except gspread.exceptions.APIError:
            # print(err)
            sheet_name = f'{option_name} | {data[0].data} | {data[5].data} | {data[8].data} ({count})'
            count += 1


def multiple_sheets_response(Folder, auth):
    """This function is designed for options that have multiple different google sheet options that
    are not statically named.

    For instance, the SQA sheets that are used change depending on which generation of robot is
    being tested. This means that there are multiple differently named sheets inside a common
    directory in google drive. This function would then search through that common directory and
    list all google sheets in that directory and allow the user to choose which sheet they would
    like to use.
    """

    sheet_files = auth.list_spreadsheet_files(folder_id=Folder)
    option_list = []

    for count, file in enumerate(sheet_files):
        logger.debug("Sheet option %d: %s", count + 1, file["name"])
        option_list.append(file)

    return option_list


#endregion

#-----------------------------------------------------------------------------------------------------------------------------
#region Main Code


def sheet_editor(auth, sheet, worksheet, config_data, option_name, robot, progress_cb=None):
    """This is the main code of the script.

    This code is responsible for polling the user to decide on what actions to be taken and for
    which sheets/worksheets to use. After the user is polled, it runs all relevant functions to
    acquire data from SWI, link it to the desired data, and then write the new information back to
    the desired  google sheet.

    Returns the newly created (duplicated) worksheet on success, or None if the run was aborted /
    failed (so callers can record it, e.g. for the RETRO history).
    """

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
        if worksheet is None:
            return

        report(0.8, "Reading sheet data...")
        values = worksheet.get(Gloss.GOOGLE_SHEET_RANGE)
        if not values:
            logger.warning("No data found in range %s", Gloss.GOOGLE_SHEET_RANGE)
            return

        report(0.9, "Writing data to sheet...")
        updated_values = data_linker(values, robot_info)
        worksheet.update(updated_values, Gloss.GOOGLE_SHEET_RANGE)

        report(1.0, "Complete!")
        webbrowser.open(worksheet.url)
        return worksheet

    except HttpError as err:
        logger.error("Google API error during sheet edit: %s", err)
        return None


# main()
