# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Drive-backed image insertion for the Sheet Editor's "Add Image" feature.

Uploads an image into a dedicated "OPS Automations Screenshots" folder in the *user's own* Google
Drive (the account gspread authorized), shares it to the user's Workspace domain ("anyone at the
domain with the link"), and writes an ``=IMAGE()`` formula into a worksheet cell -- sized so the
image's width matches the column, then growing the row so the image is fully visible.

Why domain-scoped sharing: the image is displayed via the *viewer's* logged-in Google session, so it
renders for anyone in the org who can open the sheet -- while staying fully internal (never public).
This also avoids the ``publishOutNotPermitted`` policy that blocks sharing files outside the domain.
Sharing is best-effort: if the org restricts even domain link-sharing, the image still uploads and
renders for the uploader (it just may show broken for teammates until the file is shared). There is
no API to grant Sheets' one-time per-user "Allow access" banner (see dialogs.ImageBannerReminderWindow).

There is also a one-time, per-user, per-document "Allow access" banner Sheets shows for external-data
formulas; no API can grant it (see dialogs.ImageBannerReminderWindow -- the GUI just reminds the
user to click it once).

Reuses the GUI's existing gspread OAuth credentials (spreadsheets + drive scopes) -- no extra auth.
Derived from the image_insert_spike.py proof-of-concept.
"""
import logging
import pathlib

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from gspread.utils import rowcol_to_a1
from PIL import Image

logger = logging.getLogger("OPS.drive_images")

FOLDER_NAME = "OPS Automations Screenshots"  # dedicated folder in the user's My Drive root
DEFAULT_COLUMN_WIDTH = 100  # Sheets' default column width (px), used if the API reports none
MIN_ROW_HEIGHT = 21  # Sheets' default row height (px) -- never shrink a row below this
MAX_ROW_HEIGHT = 2000  # clamp so an extreme aspect ratio can't request an absurd row height


# --------------------------------------------------------------------------------------------------
# Drive: service, folder, upload
# --------------------------------------------------------------------------------------------------
def drive_service(gc):
    """A Drive v3 service built from the gspread client's OAuth credentials (same session/scopes).

    gspread 6.x stores the google-auth credentials on the client's HTTP client (``gc.http_client.auth``).
    """
    return build("drive", "v3", credentials=gc.http_client.auth, cache_discovery=False)


def find_screenshots_folder(drive):
    """Return the id of the FOLDER_NAME folder in My Drive root, or None if it doesn't exist."""
    query = (f"name = '{FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' "
             f"and 'root' in parents and trashed = false")
    files = drive.files().list(q=query, spaces="drive",
                               fields="files(id, name)").execute().get("files", [])
    if files:
        logger.info("Found Drive folder %r (id=%s).", FOLDER_NAME, files[0]["id"])
        return files[0]["id"]
    return None


def create_screenshots_folder(drive) -> str:
    """Create the FOLDER_NAME folder in My Drive root and return its id."""
    meta = {"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}
    folder = drive.files().create(body=meta, fields="id").execute()
    logger.info("Created Drive folder %r (id=%s).", FOLDER_NAME, folder["id"])
    return folder["id"]


def upload_image(drive, folder_id: str, image_path: str) -> str:
    """Upload ``image_path`` into ``folder_id`` and return its file id (sharing is a separate
    step)."""
    media = MediaFileUpload(image_path, resumable=False)
    body = {"name": pathlib.Path(image_path).name, "parents": [folder_id]}
    file = drive.files().create(body=body, media_body=media, fields="id").execute()
    logger.info("Uploaded image (id=%s).", file["id"])
    return file["id"]


def user_domain(drive):
    """The Workspace domain of the authenticated user (e.g. 'bostondynamics.com'), or None if it
    can't be determined (personal account / API error)."""
    try:
        about = drive.about().get(fields="user(emailAddress)").execute()
        email = about.get("user", {}).get("emailAddress", "")
        return email.split("@", 1)[1] if "@" in email else None
    except Exception:  # noqa: BLE001 -- non-fatal; caller falls back to no domain share
        logger.exception("Could not determine the user's Drive domain")
        return None


def share_in_domain(drive, file_id: str, domain) -> bool:
    """Share ``file_id`` as 'anyone at ``domain`` with the link -> Viewer' (link-only, not
    discoverable) so teammates who open the sheet can see the image, while it stays internal.

    Best-effort: returns False (logged) if ``domain`` is unknown or the org restricts even domain
    link-sharing. The image still renders for the uploader regardless.
    """
    if not domain:
        return False
    try:
        drive.permissions().create(
            fileId=file_id, body={
                "type": "domain",
                "domain": domain,
                "role": "reader",
                "allowFileDiscovery": False
            }).execute()
        logger.info("Shared image %s to domain %r (link-only).", file_id, domain)
        return True
    except HttpError as e:
        logger.warning("Could not domain-share image %s to %r: %s", file_id, domain, e)
        return False


def image_url(file_id: str) -> str:
    """The Drive URL form that =IMAGE() renders most reliably (the googleusercontent CDN)."""
    return f"https://lh3.googleusercontent.com/d/{file_id}"


def image_dimensions(image_path: str):
    """(width, height) in pixels, read without loading the full image into memory for a resize."""
    with Image.open(image_path) as im:
        return im.size


# --------------------------------------------------------------------------------------------------
# Sheets: insert the =IMAGE() formula + size the row
# --------------------------------------------------------------------------------------------------
def _column_width_px(spreadsheet, worksheet, col_index: int) -> int:
    """Current pixel width of 1-based ``col_index`` on ``worksheet`` (DEFAULT_COLUMN_WIDTH if
    unset).

    Uses a tightly field-masked spreadsheets.get so the response is just this column's metadata
    rather than the whole grid.
    """
    col_letter = rowcol_to_a1(1, col_index).rstrip("0123456789")
    params = {
        "includeGridData": True,
        "ranges": [f"'{worksheet.title}'!{col_letter}1:{col_letter}1"],
        "fields": "sheets(properties(sheetId),data(columnMetadata(pixelSize)))",
    }
    meta = spreadsheet.fetch_sheet_metadata(params=params)
    for sheet in meta.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") == worksheet.id:
            col_meta = sheet.get("data", [{}])[0].get("columnMetadata", [])
            if col_meta and "pixelSize" in col_meta[0]:
                return int(col_meta[0]["pixelSize"])
    return DEFAULT_COLUMN_WIDTH


def insert_image_in_cell(spreadsheet, worksheet, row: int, col: int, url: str, img_w: int,
                         img_h: int) -> tuple:
    """Write ``=IMAGE(url, 4, height, width)`` into 1-based (row, col) sized so the image width
    equals the column width (aspect ratio preserved), then grow that row so the image is fully
    visible.

    Returns the (display_width, display_height) in px that were used.
    """
    col_w = _column_width_px(spreadsheet, worksheet, col)
    ratio = (img_h / img_w) if img_w else 1.0
    row_h = max(MIN_ROW_HEIGHT, min(MAX_ROW_HEIGHT, round(col_w * ratio)))
    cell = rowcol_to_a1(row, col)

    # Mode 4 = explicit pixel size; args are (mode, height, width).
    formula = f'=IMAGE("{url}", 4, {row_h}, {col_w})'
    worksheet.update([[formula]], cell, value_input_option="USER_ENTERED")

    spreadsheet.batch_update({
        "requests": [{
            "updateDimensionProperties": {
                "range": {
                    "sheetId": worksheet.id,
                    "dimension": "ROWS",
                    "startIndex": row - 1,
                    "endIndex": row
                },
                "properties": {
                    "pixelSize": row_h
                },
                "fields": "pixelSize",
            }
        }]
    })
    logger.info("Inserted image at %s (%dx%dpx) and set row %d height to %dpx.", cell, col_w, row_h,
                row, row_h)
    return col_w, row_h
