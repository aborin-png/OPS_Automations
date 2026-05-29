'''
This file is responsible for scanning the "global truth" STO google sheet
(Test Cells, Docks, Conveyors, Safety Systems) and building the live zone lookup
tables the GUI relies on.

It reads the "Dock/Test Cell Name" column along with the "Zone IDs for 1.0" and
"Zone IDs for 1.5" columns, parses the numeric zone id out of each cell (cells look
like "Zone 203 - TVG"), and returns:
    zone_names : {zone_id (int) -> dock/cell name (str)}
    zone_types : {zone_id (int) -> 'Dock' | 'Cell'}

The caller (UI_Handler) overwrites glossary.ZONE_NAMES / glossary.ZONE_TYPES in place
with these results, falling back to the hardcoded values in glossary.py if the scan fails.
'''
#-----------------------------------------------------------------------------------------------------------------------------

import re

import glossary as Gloss

#-----------------------------------------------------------------------------------------------------------------------------

# 0-based column indexes in the STO sheet (A=0, B=1, ...).
NAME_COL = 2        # C: Dock/Test Cell Name
ZONE_1_0_COL = 4    # E: Zone IDs for 1.0
ZONE_1_5_COL = 5    # F: Zone IDs for 1.5

HEADER_ROWS = 2     # first two rows are headers

# Matches "Zone 203", "Zone 35", "Zone203", etc. and captures the number.
ZONE_RE = re.compile(r'Zone\s*(\d+)', re.IGNORECASE)


def _classify(name):
    '''A zone is a Dock if its name starts with "Dock", otherwise it is a Cell.'''
    return 'Dock' if name.lower().startswith('dock') else 'Cell'


def scan_zone_data(auth):
    '''
    Open the STO global-truth sheet and return (zone_names, zone_types).

    Raises on any failure (network, auth, permissions, missing sheet); the caller is
    responsible for falling back to the hardcoded glossary values.
    '''
    sheet = auth.open_by_key(Gloss.STO_SHEET_KEY)
    worksheet = sheet.get_worksheet_by_id(Gloss.STO_SHEET_GID)
    rows = worksheet.get_all_values()

    zone_names = {}
    zone_types = {}

    for row in rows[HEADER_ROWS:]:
        name = row[NAME_COL].strip() if len(row) > NAME_COL else ''
        if not name:
            continue

        zone_type = _classify(name)
        for col in (ZONE_1_0_COL, ZONE_1_5_COL):
            if len(row) <= col:
                continue
            for match in ZONE_RE.finditer(row[col]):
                zone_id = int(match.group(1))
                zone_names[zone_id] = name
                zone_types[zone_id] = zone_type

    return zone_names, zone_types