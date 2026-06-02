import requests
import sys
import json
import logging

try:
    from POST_Testing import robot_password
except ImportError:
    import robot_password

logger = logging.getLogger("OPS.robot_comms")


# Post command for soft reboot using python
def soft_reboot_api(robot: str, password: str) -> None:
    """Performs a soft-reboot of the robot computer systems via POST /api/release/reboot.

    No parameters required.

    Args:
        auth_token (str): Bearer token from login_swi_api.
        robot_address (str): The address or hostname of the robot.
        logger: Logger object for logging messages.

    Raises:
        requests.HTTPError: If the request fails (400 Bad Request, 401 Unauthorized, etc).
    """
    url = f"https://{robot}.stretch/api/release/reboot"

    auth_token = get_auth_token(robot, password)
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    logger.info("Sending soft reboot request to %s", url)
    try:
        response = requests.post(url, headers=headers, verify=False, timeout=10)
        logger.debug("Soft reboot response: %s %s", response.status_code, response.text)
        response.raise_for_status()
        logger.info("Soft reboot request accepted (200 OK)")
    except requests.HTTPError as e:
        logger.error("Soft reboot failed: %s %s", e.response.status_code, e.response.text)
        raise
    except requests.RequestException as e:
        logger.error("Soft reboot request error: %s", e)
        raise

def restart_AFSE(robot: str, password: str) -> None:
    """Performs a restart of the AFSE service via POST /api/behaviors/start.

    No parameters required.

    Args:
        robot (str): The address or hostname of the robot.
        password (str): The password for the robot.

    Raises:
        requests.HTTPError: If the request fails (400 Bad Request, 401 Unauthorized, etc).
    """
    url = f"https://{robot}.stretch/api/behaviors/start"

    auth_token = get_auth_token(robot, password)
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    body = {"behaviorId": "60005", "uploadTestResults": True}
    logger.info("Sending AFSE restart request to %s", url)
    try:
        response = requests.post(url, headers=headers, json=body, verify=False, timeout=10)
        logger.debug("AFSE restart response: %s %s", response.status_code, json.dumps(response.json(), indent=4))
        response.raise_for_status()
        logger.info("AFSE restart request accepted (200 OK)")
    except requests.HTTPError as e:
        logger.error("AFSE restart failed: %s %s", e.response.status_code, e.response.text)
        raise
    except requests.RequestException as e:
        logger.error("AFSE restart request error: %s", e)
        raise

def stow_robot(robot: str, password: str) -> None:
    """Stows the robot via POST /api/behaviors/start with stow behavior.

    Args:
        robot (str): The address or hostname of the robot.
        password (str): The password for the robot.
    
    Raises:
        requests.HTTPError: If the request fails (400 Bad Request, 401 Unauthorized, etc).
    """
    url = f"https://{robot}.stretch/api/behaviors/start"
    auth_token = get_auth_token(robot, password)
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    body = {"behaviorId": "40", "uploadTestResults": True} 
    try:
        response = requests.post(url, headers=headers, json=body, verify=False, timeout=10)
        response.raise_for_status()
        logger.debug("Stow behavior start response: %s %s", response.status_code, json.dumps(response.json(), indent=4))
        logger.info("Stow behavior start request accepted (200 OK)")
    except requests.HTTPError as e:
        logger.error("Stow behavior start failed: %s %s", e.response.status_code, e.response.text)
        raise
    except requests.RequestException as e:
        logger.error("Stow behavior start request error: %s", e)
        raise

def stop_behavior(robot: str, password: str) -> None:
    """Stops the currently active behavior via POST /api/behaviors/stop.

    Args:
        robot (str): The address or hostname of the robot.
        password (str): The password for the robot.
    """
    url = f"https://{robot}.stretch/api/behaviors/stop"
    auth_token = get_auth_token(robot, password)
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    try:
        response = requests.post(url, headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        logger.info("Behavior stop request accepted (200 OK)")
    except requests.HTTPError as e:
        logger.error("Behavior stop failed: %s %s", e.response.status_code, e.response.text)
        raise
    except requests.RequestException as e:
        logger.error("Behavior stop request error: %s", e)
        raise



#-------------------------------------------------------------------------------------------------------------------

#region Auxiliary Functions

def get_auth_token(robot, password):
    url = f"https://{robot}.stretch/authd/login"
    try:
        response = requests.post(url, auth=("bd", password), verify=False, timeout=10)
        response.raise_for_status()
        token = response.json().get("auth_token")
        if not token:
            raise ValueError("No auth_token found in login response")
        return token
    except requests.RequestException as e:
        logger.error("Login request failed: %s", e)
        raise
    except ValueError as e:
        logger.error("Login response error: %s", e)
        raise

def get_behavior_list(robot, password):
    url = f"https://{robot}.stretch/api/behaviors/list"
    auth_token = get_auth_token(robot, password)
    headers = {"Authorization": f"Bearer {auth_token}"}
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        behaviors = response.json().get("behaviors", [])
        logger.info("Available behaviors: %s", behaviors)

        with open(f"{robot}_behaviors.txt", "w") as f:
            for behavior in behaviors:
                f.write(f"{behavior}\n")
        logger.info("Behavior list saved to %s_behaviors.txt", robot)
    except requests.RequestException as e:
        logger.error("Get behavior list request failed: %s", e)
        raise

def get_previously_active_behavior(robot, password):
    url = f"https://{robot}.stretch/api/behaviors/getLastBehaviorStatus"
    auth_token = get_auth_token(robot, password)
    headers = {"Authorization": f"Bearer {auth_token}"}
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        active_behavior = response.json()
        logger.info("Previously active behavior: %s", json.dumps(active_behavior, indent=4))
        return active_behavior
    except requests.RequestException as e:
        logger.error("Get active behavior request failed: %s", e)
        raise

#endregion
# if __name__ == "__main__":
#     robot = sys.argv[1] if len(sys.argv) > 1 else "None"
#     password = robot_password.get_robot_password(robot)
#     if password is None:
#         print("Failed to retrieve robot password. Cannot perform soft reboot.")
#     else:
#         # soft_reboot_api(robot, password)
#         # get_behavior_list(robot, password) 
#         # get_previously_active_behavior(robot, password)
#         # restart_AFSE(robot, password)
#         stow_robot(robot, password)
#         # stop_behavior(robot, password)
