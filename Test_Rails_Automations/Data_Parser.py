from URL_Fetch import get_test_results, get_test_title
import glossary as gloss


import pprint
import types

def results_extractor(api, project_id):
    raw_results = get_test_results(api, project_id).results
    results_list = []

    # with open('raw_results_ouptut.txt', 'wt') as file:
    #     pprint.pprint(raw_results, stream=file)

    for result in raw_results:
        # print(result)
        result = types.SimpleNamespace(**result)
        test_id = result.test_id
        status = gloss.status_codes[result.status_id]
        title = get_test_title(api, test_id)
        url = f'https://testrails.bostondynamics.com/testrail/index.php?/tests/view/{test_id}&group_by=tests:id&group_order=asc&group_id=-1'
        comment = ''
        
        if result.status_id == 5:
            for each_result in result.custom_step_results: 
                if each_result['actual'] != '':
                    comment = each_result['actual']
        
        results_list.append(gloss.Results(title   = title,
                                          id      = test_id,
                                          status  = status,
                                          url     = url,
                                          comment = comment))
        
    return results_list

                    

