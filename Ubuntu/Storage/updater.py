
import os
import requests
import logging

from diff_parser import Diff

logging.basicConfig(filename="./updater.log", level=logging.INFO)


def update(self, repo, version) -> None:
        # print(__file__)
        logging.info("Checking for Updates.")
        print('Checking for Updates.')

        GITHUB_REPO_URL=f"https://github.com/{repo.strip()}" 
        VERSION=version.strip()
        LATEST_RELEASES_URL=f"{GITHUB_REPO_URL}/releases/latest"
        LATEST_VERSION = requests.head(LATEST_RELEASES_URL).headers['location'].split("/")[-1]
        DIFF_URL=f"{GITHUB_REPO_URL}/compare/{VERSION}...{LATEST_VERSION}.diff"
        RAW_GITHUB_URL=f"https://raw.githubusercontent.com/{repo.strip()}"
        
        UPTODATE = VERSION == LATEST_VERSION

        if UPTODATE:
            logging.info("No updates found.")
            print('No updates found.')
            return False
        else:
            decision_num = input('An update was found, would you like to update? (y/n): ')
            decision = 0 if decision_num == 'y' or decision_num == 'Y' else 1
            if decision:
                return False
        
        # comapring diffs
        resp = requests.get(DIFF_URL)
        diff = Diff(resp.content.decode())
        #Mainly to prevent the auto-update code from nuking itself
        if str(resp) != "<Response [200]>":
            raise Exception(f"Maybe a network error or most likely the version/github username/repo is not correct, does this link work ?: {GITHUB_REPO_URL}/compare/{VERSION}...{LATEST_VERSION} \n")

        # downloading and installing updates
        for d in diff:
            if d.type != 'deleted':
                print(f"WRITING: .{d.new_filepath}")
                with open(f'.{d.old_filepath}', 'wb') as file:
                    resp = requests.get(f"{RAW_GITHUB_URL}/{LATEST_VERSION}{d.new_filepath}")
                    file.write(resp.content)
                if d.old_filepath != d.new_filepath:
                    if os.path.exists(f".{d.old_filepath}"):
                        os.rename(f".{d.old_filepath}", f".{d.new_filepath}")
            elif os.path.exists(f".{d.old_filepath}"):
                print(f"DELETING: .{d.old_filepath}")
                os.remove(f".{d.old_filepath}")
        
        logging.info('Update Complete!')
        print('Update Complete!')