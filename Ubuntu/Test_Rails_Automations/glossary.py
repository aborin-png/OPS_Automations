status_codes = {
    1   : 'Passed',
    2   : 'Blocked',
    3   : 'Untested',
    4   : 'Retest',
    5   : 'Failed',
    6   : 'In Progress',
    7   : 'Failed Not Blocking',
    8   : 'Not Part of Test Run',
    9   : 'Completed',
    10  : 'Meets Expectations',
    11  : 'Not Sufficient to Standard',
    12  : 'Exploratory',
}

class Results:
    def __init__(self, title, id, status, url, comment = ''):
        self.title = title
        self.id = id
        self.status = status
        self.url = url
        self.comment = comment
        