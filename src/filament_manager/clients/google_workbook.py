"""Bounded Google REST publication with stable tabs and atomic staged replacement."""

import asyncio
import json
import re
import secrets
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import httpx

from filament_manager.clients.google_sheets import GoogleSheetsError
from filament_manager.services.google_workbook import WorkbookTab, cell

SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE = "https://www.googleapis.com/drive/v3/files"
NAVY = {"red": 22 / 255, "green": 50 / 255, "blue": 79 / 255}
TEAL = {"red": 47 / 255, "green": 128 / 255, "blue": 165 / 255}
PALE = {"red": 247 / 255, "green": 250 / 255, "blue": 252 / 255}
WHITE = {"red": 1, "green": 1, "blue": 1}
GOLD = {"red": 148 / 255, "green": 96 / 255, "blue": 24 / 255}
META_KEY = "filament_manager_publication"


class GoogleWorkbookClient:
    """Only fixed Google endpoints and validated file IDs can receive the bearer."""

    def __init__(self, token: str, publication_key: str) -> None:
        self.token = token
        self.publication_key = publication_key
        self._last_request_at = 0.0

    async def request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """Bound requests; provider bodies are neither logged nor retained."""
        if not url.startswith((SHEETS, DRIVE)):
            raise GoogleSheetsError("Google request destination is invalid.")
        # Stay below Google's per-user minute quota even for a large snapshot.
        # One publisher holds the database lock; this wait blocks no event loop.
        delay = max(0.0, 1.25 - (time.monotonic() - self._last_request_at))
        if delay:
            await asyncio.sleep(delay)
        self._last_request_at = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
                response = await client.request(
                    method, url, headers={"Authorization": f"Bearer {self.token}"}, **kwargs
                )
            if response.status_code == 429:
                raise GoogleSheetsError("Google rate limit reached. Publication will retry automatically.")
            if response.status_code in (401, 403):
                raise GoogleSheetsError(
                    "Google access was denied. Check enabled APIs, consent, and workbook access."
                )
            if response.status_code == 404:
                raise GoogleSheetsError(
                    "The Google workbook is unavailable. Restore it from Drive trash or check its access."
                )
            if not 200 <= response.status_code < 300 or len(response.content) > 8_000_000:
                raise ValueError
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError
            return body
        except (httpx.HTTPError, ValueError):
            raise GoogleSheetsError(
                "Google publication failed. The worker will retry; check Diagnostics if it persists."
            ) from None

    @staticmethod
    def file_id(value: Any) -> str:
        """Reject paths, queries, and unexpected provider identity formats."""
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", value):
            raise GoogleSheetsError("Google returned an invalid workbook identity.")
        return value

    async def find_or_create(self) -> str:
        """Recover an app-created workbook after a crash without matching by name."""
        found = await self.request(
            "GET",
            DRIVE,
            params={
                "q": (
                    "trashed = false and appProperties has { key='filament_manager' "
                    f"and value='{self.publication_key}' }}"
                ),
                "fields": "files(id)",
                "pageSize": 2,
            },
        )
        files = found.get("files", [])
        if len(files) > 1:
            raise GoogleSheetsError(
                "More than one app workbook has this identity. Resolve the duplicate in Drive."
            )
        if files:
            return self.file_id(files[0]["id"])
        created = await self.request(
            "POST",
            DRIVE,
            params={"fields": "id"},
            json={
                "name": "Filament Manager",
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "appProperties": {"filament_manager": self.publication_key},
            },
        )
        return self.file_id(created.get("id"))

    async def batch(self, spreadsheet: str, requests: list[dict[str, Any]]) -> None:
        """Apply one atomic batch; never automatically replay uncertain writes."""
        await self.request(
            "POST", f"{SHEETS}/{self.file_id(spreadsheet)}:batchUpdate", json={"requests": requests}
        )

    async def publish(self, spreadsheet: str, tables: list[WorkbookTab]) -> None:
        """Stage all values, then replace managed contents in one atomic batch.

        Existing tab IDs remain stable, unrelated tabs are untouched, and stale
        rows disappear. Failed staging leaves the last complete publication.
        """
        spreadsheet = self.file_id(spreadsheet)
        base = f"{SHEETS}/{spreadsheet}"
        document = await self.request(
            "GET",
            base,
            params={
                "fields": (
                    "sheets(properties,developerMetadata,bandedRanges,protectedRanges,charts),properties.title"
                ),
            },
        )
        existing = document.get("sheets", [])
        managed = {
            item["properties"]["title"]: item
            for item in existing
            if any(
                meta.get("metadataKey") == META_KEY and meta.get("metadataValue") == self.publication_key
                for meta in item.get("developerMetadata", [])
            )
        }
        stage_prefix = f"_fm_{self.publication_key}_"
        stale = [
            item
            for item in existing
            if any(
                meta.get("metadataKey") == META_KEY + "_stage"
                and meta.get("metadataValue") == self.publication_key
                for meta in item.get("developerMetadata", [])
            )
        ]
        if stale:
            await self.batch(
                spreadsheet, [{"deleteSheet": {"sheetId": item["properties"]["sheetId"]}} for item in stale]
            )
        overview = WorkbookTab(
            "Dashboard",
            ["collection", "records", "publication"],
            [[tab.title, len(tab.rows), "Open table"] for tab in tables],
        )
        overview.rows += [
            ["Last published (UTC)", datetime.now(UTC).isoformat(), "Filament Manager"],
            ["Authority", "App → Google only", "Edit in the app, then Sync now."],
            ["Search and filter", "Ctrl+F / column filters", "Create a filter view for your own analysis."],
            [
                "Privacy",
                "Business records only",
                "Credentials, accounts, security logs, connection URLs, images and files excluded.",
            ],
            [
                "History",
                "Archived records included",
                "Settings and Evidence contains complete nested print/template/calibration values.",
            ],
        ]
        products = next((tab for tab in tables if tab.title == "Filaments"), None)
        inventory = next((tab for tab in tables if tab.title == "Spools"), None)
        material_counts: Counter[str] = Counter()
        if products and inventory and "filament_product_id" in inventory.fields:
            materials = {str(row[0]): row[products.fields.index("material_type")] for row in products.rows}
            for row in inventory.rows:
                spool_values = dict(zip(inventory.fields, row, strict=True))
                if not spool_values.get("archived"):
                    material_counts[
                        str(materials.get(str(spool_values["filament_product_id"]), "Unknown"))
                    ] += 1
            remaining = sum(
                float(row[inventory.fields.index("remaining_mass_effective_g")])
                for row in inventory.rows
                if not row[inventory.fields.index("archived")]
            )
            overview.rows.append(["Remaining filament (g)", remaining, "Non-archived spools"])
        chart_start = len(overview.rows) + 1
        overview.rows.extend(
            [material, count, "Non-archived spools"] for material, count in sorted(material_counts.items())
        )
        tabs = [overview, *tables]
        used_ids = {item["properties"]["sheetId"] for item in existing}

        def new_id() -> int:
            while (value := secrets.randbelow(2_000_000_000) + 1) in used_ids:
                pass
            used_ids.add(value)
            return value

        destinations: dict[str, int] = {}
        stages: dict[str, int] = {}
        prepare: list[dict[str, Any]] = []
        occupied_titles = {item["properties"]["title"] for item in existing}
        for tab in tabs:
            if tab.title in occupied_titles and tab.title not in managed:
                raise GoogleSheetsError(
                    "A workbook tab conflicts with an app table. Rename that unmanaged tab, then sync again."
                )
            target_id = managed[tab.title]["properties"]["sheetId"] if tab.title in managed else new_id()
            destinations[tab.title] = target_id
            stage_id = stages[tab.title] = new_id()
            if tab.title not in managed:
                prepare.extend(
                    [
                        {
                            "addSheet": {
                                "properties": {
                                    "sheetId": target_id,
                                    "title": tab.title,
                                    "gridProperties": {"rowCount": 1, "columnCount": len(tab.fields)},
                                }
                            }
                        },
                        {
                            "createDeveloperMetadata": {
                                "developerMetadata": {
                                    "metadataKey": META_KEY,
                                    "metadataValue": self.publication_key,
                                    "location": {"sheetId": target_id},
                                    "visibility": "DOCUMENT",
                                }
                            }
                        },
                    ]
                )
            prepare.append(
                {
                    "addSheet": {
                        "properties": {
                            "sheetId": stage_id,
                            "title": f"{stage_prefix}{stage_id}",
                            "hidden": True,
                            "gridProperties": {
                                "rowCount": max(2, len(tab.rows) + 1),
                                "columnCount": len(tab.fields),
                            },
                        }
                    }
                }
            )
            prepare.append(
                {
                    "createDeveloperMetadata": {
                        "developerMetadata": {
                            "metadataKey": META_KEY + "_stage",
                            "metadataValue": self.publication_key,
                            "location": {"sheetId": stage_id},
                            "visibility": "DOCUMENT",
                        }
                    }
                }
            )
        await self.batch(spreadsheet, prepare)
        # Exact UUID links connect inventory, settings, calibration and history.
        identities = {
            str(row[0]): (destinations[tab.title], i + 2)
            for tab in tables
            if tab.fields[0] == "id"
            for i, row in enumerate(tab.rows)
        }
        batches: list[dict[str, Any]] = []
        size = 0
        for tab in tabs:
            header_labels = [
                name.replace("vendor_id", "manufacturer_id").replace("_", " ").title() for name in tab.fields
            ]
            all_rows = [header_labels, *tab.rows]
            for offset in range(0, len(tab.rows) + 1, 100):
                source_rows = all_rows[offset : offset + 100]
                data_rows = []
                for index, row in enumerate(source_rows, offset):
                    values = []
                    for column, value in enumerate(row):
                        linked_record = identities.get(str(value)) if index else None
                        link = (
                            f"https://docs.google.com/spreadsheets/d/{spreadsheet}/edit"
                            f"#gid={linked_record[0]}&range=A{linked_record[1]}"
                            if linked_record
                            else None
                        )
                        if tab.title == "Dashboard" and index and column == 0 and value in destinations:
                            link = f"https://docs.google.com/spreadsheets/d/{spreadsheet}/edit#gid={destinations[value]}"
                        values.append(cell(value, link=link))
                    data_rows.append({"values": values})
                for request in cell_updates(stages[tab.title], data_rows, offset):
                    length = len(json.dumps(request).encode())
                    if batches and (size + length > 1_500_000 or len(batches) >= 200):
                        await self.batch(spreadsheet, batches)
                        batches, size = [], 0
                    batches.append(request)
                    size += length
        if batches:
            await self.batch(spreadsheet, batches)
        finish: list[dict[str, Any]] = []
        for index, tab in enumerate(tabs):
            target, stage = destinations[tab.title], stages[tab.title]
            rows, columns = max(2, len(tab.rows) + 1), len(tab.fields)
            whole = {
                "sheetId": target,
                "startRowIndex": 0,
                "endRowIndex": rows,
                "startColumnIndex": 0,
                "endColumnIndex": columns,
            }
            header = {**whole, "endRowIndex": 1}
            for band in managed.get(tab.title, {}).get("bandedRanges", []):
                finish.append({"deleteBanding": {"bandedRangeId": band["bandedRangeId"]}})
            finish.extend(
                [
                    {"clearBasicFilter": {"sheetId": target}},
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": target,
                                "index": index,
                                "gridProperties": {
                                    "rowCount": rows,
                                    "columnCount": max(12, columns) if tab.title == "Dashboard" else columns,
                                    "frozenRowCount": 1,
                                    "frozenColumnCount": 2 if tab.fields[0] == "id" else 1,
                                },
                                "tabColorStyle": {"rgbColor": TEAL if index else GOLD},
                            },
                            "fields": "index,gridProperties,tabColorStyle",
                        }
                    },
                    {"updateCells": {"range": whole, "fields": "userEnteredValue,userEnteredFormat,note"}},
                    {
                        "copyPaste": {
                            "source": {**whole, "sheetId": stage},
                            "destination": whole,
                            "pasteType": "PASTE_NORMAL",
                        }
                    },
                    {
                        "repeatCell": {
                            "range": whole,
                            "cell": {
                                "userEnteredFormat": {
                                    "wrapStrategy": "CLIP",
                                    "verticalAlignment": "MIDDLE",
                                    "numberFormat": {"type": "NUMBER", "pattern": "0.##"},
                                    "textFormat": {"fontFamily": "Arial", "fontSize": 10},
                                }
                            },
                            "fields": (
                                "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment,"
                                "userEnteredFormat.numberFormat,userEnteredFormat.textFormat.fontFamily,"
                                "userEnteredFormat.textFormat.fontSize"
                            ),
                        }
                    },
                    {
                        "repeatCell": {
                            "range": header,
                            "cell": {
                                "userEnteredFormat": {
                                    "backgroundColor": NAVY,
                                    "textFormat": {"bold": True, "foregroundColor": WHITE},
                                }
                            },
                            "fields": (
                                "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.bold,"
                                "userEnteredFormat.textFormat.foregroundColor"
                            ),
                        }
                    },
                    {"setBasicFilter": {"filter": {"range": whole}}},
                    {
                        "addBanding": {
                            "bandedRange": {
                                "range": whole,
                                "rowProperties": {
                                    "headerColor": NAVY,
                                    "firstBandColor": WHITE,
                                    "secondBandColor": PALE,
                                },
                            }
                        }
                    },
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": target,
                                "dimension": "COLUMNS",
                                "startIndex": 0,
                                "endIndex": columns,
                            },
                            "properties": {"pixelSize": 185},
                            "fields": "pixelSize",
                        }
                    },
                    {"deleteSheet": {"sheetId": stage}},
                ]
            )
            if not managed.get(tab.title, {}).get("protectedRanges"):
                finish.append(
                    {
                        "addProtectedRange": {
                            "protectedRange": {
                                "range": {"sheetId": target},
                                "description": (
                                    "Published by Filament Manager. Edit in the app; "
                                    "synchronization overwrites this table."
                                ),
                                "warningOnly": True,
                            }
                        }
                    }
                )
            if tab.fields[0] == "id":
                finish.append(
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": target,
                                "dimension": "COLUMNS",
                                "startIndex": 0,
                                "endIndex": 1,
                            },
                            "properties": {"hiddenByUser": True},
                            "fields": "hiddenByUser",
                        }
                    }
                )
        for chart in managed.get("Dashboard", {}).get("charts", []):
            finish.append({"deleteEmbeddedObject": {"objectId": chart["chartId"]}})
        if material_counts:
            chart_range = {
                "sheetId": destinations["Dashboard"],
                "startRowIndex": chart_start,
                "endRowIndex": chart_start + len(material_counts),
            }
            finish.append(
                {
                    "addChart": {
                        "chart": {
                            "spec": {
                                "title": "Spools by material",
                                "pieChart": {
                                    "legendPosition": "RIGHT_LEGEND",
                                    "pieHole": 0.6,
                                    "domain": {
                                        "sourceRange": {
                                            "sources": [
                                                {**chart_range, "startColumnIndex": 0, "endColumnIndex": 1}
                                            ]
                                        }
                                    },
                                    "series": {
                                        "sourceRange": {
                                            "sources": [
                                                {**chart_range, "startColumnIndex": 1, "endColumnIndex": 2}
                                            ]
                                        }
                                    },
                                },
                            },
                            "position": {
                                "overlayPosition": {
                                    "anchorCell": {
                                        "sheetId": destinations["Dashboard"],
                                        "rowIndex": 1,
                                        "columnIndex": 4,
                                    },
                                    "widthPixels": 650,
                                    "heightPixels": 380,
                                }
                            },
                        }
                    }
                }
            )
        await self.batch(spreadsheet, finish)


def cell_updates(
    sheet: int, rows: list[dict[str, Any]], offset: int, column: int = 0
) -> list[dict[str, Any]]:
    """Split large text batches in either dimension without truncating cells."""
    request = {
        "updateCells": {
            "start": {"sheetId": sheet, "rowIndex": offset, "columnIndex": column},
            "rows": rows,
            "fields": "userEnteredValue,userEnteredFormat",
        }
    }
    if len(json.dumps(request).encode()) <= 1_000_000:
        return [request]
    if len(rows) > 1:
        middle = len(rows) // 2
        return cell_updates(sheet, rows[:middle], offset, column) + cell_updates(
            sheet, rows[middle:], offset + middle, column
        )
    values = rows[0]["values"]
    if len(values) < 2:
        raise GoogleSheetsError("A workbook cell exceeds the safe request size.")
    middle = len(values) // 2
    return cell_updates(sheet, [{"values": values[:middle]}], offset, column) + cell_updates(
        sheet, [{"values": values[middle:]}], offset, column + middle
    )
