# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Fire a "RETRO" log against a Stretch robot via SWI.

A RETRO captures the robot's recent operating data. ``take_retro_log_with_comment`` hits the
``create-support-ticket`` (comment) and ``create-retro-log`` endpoints on the robot with the same
message. Both endpoints are ``skipAuth`` on SWI, so no robot password is required.

Importable from the GUI (the CLI block only runs when executed directly).
"""
import logging

import requests

logger = logging.getLogger("OPS.retro_logging")

# Robot certs are self-signed; verify=False is expected. Silence the per-call InsecureRequestWarning.
requests.packages.urllib3.disable_warnings(
    requests.packages.urllib3.exceptions.InsecureRequestWarning)


def take_retro_log_with_comment(robot_address, retro_message):

    url_retro = f"https://{robot_address}/api/workflows/create-retro-log"
    url_comment = f"https://{robot_address}/api/workflows/create-support-ticket"
    headers = {"Content-Type": "application/json"}
    payload = {"message": retro_message}
    response_comment = requests.post(url=url_comment, headers=headers, json=payload, verify=False)
    response_retro = requests.post(url=url_retro, headers=headers, json=payload, verify=False)
    response_retro.raise_for_status()
    response_comment.raise_for_status()
    return {"retro_response": response_retro, "comment_response": response_comment}
