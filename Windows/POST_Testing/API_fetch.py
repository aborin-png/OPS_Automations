'''
This file is specifically for scrapping information off of SWI.
Although it is currently configured to only scrape robot-info data, the system is 
designed with future automation in mind. 
Scraping data from many aspects of SWI can be added fairly easily
'''

#-----------------------------------------------------------------------------------------------------------------------------
#region Includes

import logging

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("OPS.api_fetch")

#endregion
#-----------------------------------------------------------------------------------------------------------------------------
#region API_Fetch

def API_Fetch(robot, robot_offline):

    # robot = input("Please enter which robot you would like info on: ")

    # url = f"https://{robot}.stretch/api/info/robot-info"
    url = "https://internal.bosdyn.com/robot-password/lookup?serial=ssd-122341400713"

    try: 
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(url, verify=False, timeout=1)
        response.raise_for_status()
        # print(response.text)
        soup = BeautifulSoup(response.text, 'html.parser')

        text = soup.get_text(separator = '\n', strip=True)
        logger.debug("API_Fetch(%s) returned %d chars", robot, len(text))
        return text

    except requests.exceptions.RequestException as e:
        if robot in robot_offline:
            return None
        else:
            logger.warning("Error accessing %s: %s (is the robot on and not booting?)", url, e)
            return None


API_Fetch("",[])