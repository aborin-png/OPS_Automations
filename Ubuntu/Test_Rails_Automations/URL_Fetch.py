from pathlib import Path
import json
import types
import pprint

# from testrail_api import TestRailAPI

import testrail

URL = 'https://testrails.bostondynamics.com/testrail/'
EMAIL = 'aborin@bostondynamics.com'
PASS_KEY = 'mHzLdTiBy9qQp./Zq2yu-INtzPDq98xr4zwDrrP2s'


def api_connect():
    api = testrail.APIClient(URL)

    api.user = EMAIL
    api.password = PASS_KEY

    return api


def get_test_results(api, project_id):
    
    run = api.send_get(f'get_results_for_run/{project_id}')
    run = types.SimpleNamespace(**run)
    # with open('api_ouptut.txt', 'wt') as file:
    #     pprint.pprint(run, stream=file)

    return run


def get_test_title(api, test_id):

    return types.SimpleNamespace(**api.send_get(f'get_test/{test_id}')).title





# if __name__ == '__main__':
#     pprint.pprint(get_test_results())