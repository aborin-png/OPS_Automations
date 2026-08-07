# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
import json
import logging

import requests
from glossary import ROBOT_BEHAVIORS

logger = logging.getLogger("OPS.robot_comms")

RESPONSE_STATUS_CODES = {
    "200":
        "OK - The request was successful and the server responded with the requested data.",
    "400":
        "Bad Request - The server could not understand the request due to an invalid payload format",
}


def status_code_meaning(status_code):
    """Returns a human-readable meaning of the given HTTP status code."""
    status_code_str = str(status_code)

    if status_code_str.startswith("5"):
        return "Unexpected Error - The server encountered an unexpected condition that prevented it from fulfilling the request."
    else:
        return RESPONSE_STATUS_CODES.get(status_code_str, "Unexpected Status Code")


# Post command for soft reboot using python
def soft_reboot_api(robot: str, password: str) -> None:
    """Performs a soft-reboot of the robot computer systems via POST /api/release/reboot.

    No parameters required.

    Args:
        auth_token (str): Bearer token from login_swi_api.
        robot_address (str): The address or hostname of the robot.
        logger: Logger object for logging messages.

    Raises:
        requests.HTTPError: If the request fails (400 Bad Request or 5XX Unexpected Error).
    """
    url = f"https://{robot}.stretch/api/release/reboot"

    auth_token = get_auth_token(robot, password)
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    logger.info("Sending soft reboot request to %s", url)
    try:
        response = requests.post(url, headers=headers, verify=False, timeout=10)
        logger.debug("Soft reboot response: %s %s", response.status_code, response.text)
        response.raise_for_status()
        logger.info(status_code_meaning(response.status_code))
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
        requests.HTTPError: If the request fails (400 Bad Request or 5XX Unexpected Error).
    """
    url = f"https://{robot}.stretch/api/behaviors/start"

    auth_token = get_auth_token(robot, password)
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    body = {"behaviorId": ROBOT_BEHAVIORS["AFSE"], "uploadTestResults": True}
    logger.info("Sending AFSE restart request to %s", url)
    try:
        response = requests.post(url, headers=headers, json=body, verify=False, timeout=10)
        logger.debug("AFSE restart response: %s %s", response.status_code,
                     json.dumps(response.json(), indent=4))
        response.raise_for_status()

        logger.info(status_code_meaning(response.status_code))
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
        requests.HTTPError: If the request fails (400 Bad Request or 5XX Unexpected Error).
    """
    url = f"https://{robot}.stretch/api/behaviors/start"
    auth_token = get_auth_token(robot, password)
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    body = {"behaviorId": ROBOT_BEHAVIORS["STOW"], "uploadTestResults": True}
    try:
        response = requests.post(url, headers=headers, json=body, verify=False, timeout=10)
        response.raise_for_status()
        logger.debug("Stow behavior start response: %s %s", response.status_code,
                     json.dumps(response.json(), indent=4))
        logger.info(status_code_meaning(response.status_code))
    except requests.HTTPError as e:
        logger.error("Stow behavior start failed: %s %s", e.response.status_code, e.response.text)
        raise
    except requests.RequestException as e:
        logger.error("Stow behavior start request error: %s", e)
        raise


#-------------------------------------------------------------------------------------------------------------------

#region Auxiliary Functions


def get_auth_token(robot, password):
    """Retrieves the authentication token for the specified robot.

    Args:
        robot (str): The address or hostname of the robot.
        password (str): The password for the robot.

    Returns:
        str: The authentication token.
    """
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


def password_is_valid(robot: str, password: str) -> bool:
    """Confirm a candidate bd password without changing the robot's behavior.

    Attempts a login only (``get_auth_token``); a returned token means the password is valid. Any
    request/response error -- a wrong password (HTTP 401), an unreachable robot, a malformed
    response -- is treated as "not valid". Used to verify a newly entered password before it is saved
    to the encrypted store.

    Args:
        robot (str): The address or hostname of the robot.
        password (str): The candidate bd password to check.

    Returns:
        bool: True if the password authenticates, False otherwise.
    """
    try:
        return bool(get_auth_token(robot, password))
    except (requests.RequestException, ValueError):
        return False


#endregion
