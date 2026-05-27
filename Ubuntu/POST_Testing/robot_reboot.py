import requests


# Post command for soft reboot using python
def soft_reboot_api(auth_token: str, robot_address: str, logger) -> None:
    """Performs a soft-reboot of the robot computer systems via POST /api/release/reboot.

    No parameters required.

    Args:
        auth_token (str): Bearer token from login_swi_api.
        robot_address (str): The address or hostname of the robot.
        logger: Logger object for logging messages.

    Raises:
        requests.HTTPError: If the request fails (400 Bad Request, 401 Unauthorized, etc).
    """
    url = f"https://{robot_address}/api/release/reboot"
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    logger.info(f"Sending soft reboot request to {url}")
    try:
        response = requests.post(url, headers=headers, verify=False, timeout=10)
        logger.info(f"Soft reboot response: {response.status_code} {response.text}")
        response.raise_for_status()
        logger.info("Soft reboot request accepted (200 OK)")
    except requests.HTTPError as e:
        logger.error(f"Soft reboot failed: {e.response.status_code} {e.response.text}")
        raise
    except requests.RequestException as e:
        logger.error(f"Soft reboot request error: {e}")
        raise
# Equivalent curl command
curl -k -X POST https://ROBOT_ADDRESS/api/release/reboot \
  -H "Authorization: Bearer AUTH_TOKEN" \
  -H "Content-Type: application/json"
# For getting the bearer token:
curl -k -X POST -u "username:password" https://ROBOT_ADDRESS/authd/login
