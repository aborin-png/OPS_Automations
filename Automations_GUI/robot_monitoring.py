# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Behaviour / logic for the "Robot Monitoring" tab.

This is a mixin whose methods become part of the App class (see UI_Handler.py). It holds only the
tab's *functionality* -- polling each monitored robot's API, the periodic refresh loop, and adding
/ removing robots from the persisted config. The widgets (card grid, buttons, robot detail windows)
are built and wired by ``App.build_robot_monitoring`` / ``_render_robot_cards`` / ``_open_*`` in
UI_Handler.py, so every method here operates on ``self`` (the App instance).
"""
import logging
import threading

import glossary
import logger_setup
from logger_setup import log_calls
from Sheets_Automation import API_fetch, Info_Parser

STATUS_COLORS = glossary.STATUS_COLORS
CHARGE_STATUS = glossary.CHARGE_STATUS
ZONE_NAMES = glossary.ZONE_NAMES
# Same configured "OPS" logger that UI_Handler set up via logger_setup.setup_logging().
logger = logging.getLogger(logger_setup.LOGGER_NAME)


class RobotMonitoringMixin:
    """Robot Monitoring tab logic. Mixed into App; relies on widgets built by
    build_robot_monitoring.

    Uses ``self.robot_offline`` (initialised in App.__init__) as the shared set of currently
    unreachable robots, and ``self.save_config()`` to persist config changes. The monitored-robot
    list is persisted under the legacy ``config['AFSE']`` key (kept as-is for backward compatibility
    with existing user configs).
    """

    def get_robot_api(self):
        robot_api = []
        robot_list = self.config['AFSE']['Robots']

        for robot in robot_list:
            # Treat any robot whose API is unreachable OR whose payload is missing
            # expected fields as offline, so one malformed robot can't blank the whole list.
            offline_entry = [robot, 0, 5, 5, 'None']
            try:
                api = API_fetch.API_Fetch(robot, self.robot_offline)
                if api is None:
                    raise ValueError("no API response")

                info = Info_Parser.info_parser(api)

                if robot in self.robot_offline:
                    self.robot_offline.remove(robot)
                robot_api.append([
                    info.nickname or robot, info.soc, info.lighting_color, info.charger_mode,
                    info.connected_zone_id
                ])
            except Exception:
                if robot not in self.robot_offline:
                    self.robot_offline.append(robot)
                robot_api.append(offline_entry)

        return robot_api

    def schedule_robot_refresh(self):
        threading.Thread(target=self.robot_refresh, daemon=True).start()

    def robot_refresh(self):
        robot_api = self.fetch_robot_data()
        self.after(0, lambda: self.apply_robot_refresh(robot_api))

    def apply_robot_refresh(self, robot_api):
        if robot_api is not None:
            # The robot count changes when a robot is added (or first appears), so the
            # card grid has to be rebuilt; otherwise update the existing cards in place.
            if len(robot_api) != len(self.robot_instances):
                self._render_robot_cards(robot_api)
            else:
                self.latest_robot_api = robot_api
                for i, (name, charge, color_code, charge_code, zone_id) in enumerate(robot_api):
                    status_color, status_label = STATUS_COLORS[color_code]
                    charge_color, charge_status = CHARGE_STATUS[charge_code]

                    win = self._robot_detail_windows.get(name)
                    if win is not None and win.winfo_exists():
                        win.update_data(charge, color_code, charge_code, zone_id)

                    self.robot_instances[i][0].configure(text=f'{charge:.0f}%')
                    self.robot_instances[i][1].configure(fg_color=status_color)
                    self.robot_instances[i][2].configure(text=status_label)
                    self.robot_instances[i][3].configure(text=charge_status,
                                                         text_color=charge_color)
                    zone_text = ZONE_NAMES.get(zone_id, 'Not in a Zone')
                    self.robot_instances[i][4].configure(text=zone_text)
        self.after(5000, self.schedule_robot_refresh)

    def fetch_robot_data(self):
        try:
            robot_api = self.get_robot_api()
        except Exception:
            logger.exception("Failed to fetch robot API data")
            robot_api = None

        return robot_api

    @log_calls
    def _add_robot_to_config(self, name):
        """Persist a new robot to the monitored-robot list (config['AFSE']) and refresh the tab.

        Runs on the main thread (invoked from AddRobotWindow after a successful reachability check).
        """
        self.config['AFSE']['Robots'].append(name)
        self.save_config()
        self._reload_robots()

    @log_calls
    def _remove_robot_from_config(self, name):
        """Strip a robot from the monitored-robot list (config['AFSE']), persist, and refresh the
        tab."""
        robots = self.config['AFSE']['Robots']
        if name in robots:
            robots.remove(name)
        if name in self.robot_offline:
            self.robot_offline.remove(name)
        self.save_config()
        self._reload_robots()

    @log_calls
    def _reload_robots(self):
        """One-shot fetch + re-render so a newly added robot shows immediately, without starting a
        second refresh loop (the existing 5s loop keeps running)."""

        def work():
            robot_api = self.fetch_robot_data()
            self.after(0, lambda: self._render_robot_cards(robot_api))

        threading.Thread(target=work, daemon=True).start()
