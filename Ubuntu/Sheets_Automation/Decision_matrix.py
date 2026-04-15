import datetime
import gspread

from Info_Parser import get_config
# from Sheets_editor import authenticator


def multiple_sheets_response(Folder, auth):
    # gsheet = authenticator()

    sheet_files = auth.list_spreadsheet_files(folder_id = Folder)
    option_list = []

    for count, file in enumerate(sheet_files):
        print(f'{count + 1}: {file['name']}')
        option_list.append(file)

    while True:
            user_in = int(input('Please select which Google Sheet you like to use: ')) - 1
            
            if user_in + 1 <= len(option_list):
                sheet = option_list[user_in]['name']
                break 
            else:
                print('This is not a valid option.')

    return sheet


#TODO: needs to return a list

def decision_handler(auth):
    config_options = get_config().Options
    option_list = []
    count = 0
    
    for option, data in vars(config_options).items():
        option_list.append([option, data])
        print(f'{count+1}: {option}')
        count += 1

    selected_option = option_list[int(input('Please select which Google Sheet option you would like to use: ')) - 1][1]
    sheet = selected_option.Sheet


    if hasattr(sheet, 'Template'):
        response = input(f'A template Sheet is present ("{sheet.Template}"), would you like to create a new Google sheet? (y/n): ')
        sheet = sheet.Template if response == 'y' or response == 'Y' else multiple_sheets_response(sheet.Folder, auth)
    
    if sheet == 'Robustness SQA testing sheet':
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
    

    return [sheet, worksheet, data]
