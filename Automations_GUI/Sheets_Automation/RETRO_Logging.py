# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Fire a "RETRO" log against a Stretch robot via SWI.

A RETRO captures the robot's recent operating data. It is split across two independent ``skipAuth``
SWI endpoints (neither needs a robot password) so the GUI can fire them at different times:

  * ``take_retro_log``     -> POST ``create-retro-log``       (the data capture)
  * ``take_retro_comment`` -> POST ``create-support-ticket``  (the human-written message)

The GUI fires ``take_retro_log`` the instant the RETRO button is pressed -- capturing the event's
recent-data window immediately -- and fires ``take_retro_comment`` later, once the user has finished
typing their message and hit submit. Capturing the data first means we don't lose the event's data
during the seconds the user spends composing the message.

Importable from the GUI.
"""
import logging

import requests

logger = logging.getLogger("OPS.retro_logging")

# Robot certs are self-signed; verify=False is expected. Silence the per-call InsecureRequestWarning.
requests.packages.urllib3.disable_warnings(
    requests.packages.urllib3.exceptions.InsecureRequestWarning)

_HEADERS = {"Content-Type": "application/json"}


def take_retro_log(robot_address, message=""):
    """POST the ``create-retro-log`` (data-capture) request to the robot and return the response.

    Fired the moment the RETRO button is pressed -- before the user's message exists -- so
    ``message`` defaults to empty; the human-written text travels with the comment
    (``take_retro_comment``) instead. Raises on a non-2xx response.
    """
    url = f"https://{robot_address}/api/workflows/create-retro-log"
    response = requests.post(url=url, headers=_HEADERS, json={"message": message}, verify=False)
    response.raise_for_status()
    return response


def take_retro_comment(robot_address, message):
    """POST the ``create-support-ticket`` (comment) request carrying the user's ``message``.

    Sent on submit, after the data-capturing retro-log has already fired. Raises on a non-2xx
    response.
    """
    url = f"https://{robot_address}/api/workflows/create-support-ticket"
    response = requests.post(url=url, headers=_HEADERS, json={"message": message}, verify=False)
    response.raise_for_status()
    return response