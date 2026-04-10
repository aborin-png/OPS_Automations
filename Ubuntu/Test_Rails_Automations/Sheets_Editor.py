import URL_Fetch
import Data_Parser

import gspread

TITLE = 'B3'
FAILED = 'D10'
COPY = 'M6'


def results_organizer(results):
    failed = []
    passed = []
    in_between = []
    
    for result in results:
        if result.status == 'Failed':
            failed.append(result)
        elif result.status == 'Passed':
            passed.append(result)
        else:
            in_between.append(result)
    
    return [failed, passed, in_between]

def sheets_populator(data, worksheet):
    to_write = []

    for category in data:
        #per test case
        
        for test in category:
            #per line
            to_write.append([f'=HYPERLINK("{test.url}","{test.title}")', str(test.id), test.status, test.comment])

    worksheet.update(to_write, FAILED)

if __name__ == '__main__':
    project_id = int(input('Please input the id of the test rails project/suite: '))
    api = URL_Fetch.api_connect() 

    results = Data_Parser.results_extractor(api, project_id)
    organized_results = results_organizer(results=results)

    sheet = gspread.oauth(credentials_filename= 'credentials.json').open(title='Weekly Master Robustness Results')
    worksheet_template = sheet.worksheet('TEST RAILS TEMPLATE')
    
    suite_title = api.send_get(f'get_run/{project_id}')['name']
    worksheet = sheet.duplicate_sheet(worksheet_template.id, 1, new_sheet_name=suite_title)

    worksheet.update([[suite_title]], TITLE)
    sheets_populator(organized_results, worksheet=worksheet)
    
    
    # print(f'Title: {result.title} | ID: {result.id} | Status: {result.status} | URL: {result.url} | Comment: {result.comment}\n')

    