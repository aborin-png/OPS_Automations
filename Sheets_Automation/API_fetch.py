'''
This file is specifically for scrapping information off of SWI.
Although it is currently configured to only scrape robot-info data, the system is 
designed with future automation in mind. 
Scraping data from many aspects of SWI can be added fairly easily
'''

#-----------------------------------------------------------------------------------------------------------------------------

import requests
from bs4 import BeautifulSoup

#-----------------------------------------------------------------------------------------------------------------------------

def API_Fetch():

    robot = input("Please enter which robot you would like info on: ")

    url = f"https://{robot}.stretch/api/info/robot-info"

    try: 
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(url, verify= False)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        text = soup.get_text(separator = '\n', strip=True)

        return text
    
    except requests.exceptions.RequestException as e:
        print(f"Encountered an error when accessing the url: {e}")
        return None


