"""One-way Google Sheets publication client."""

import asyncio
from pathlib import Path
from typing import Any, cast

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build  # type: ignore[import-untyped]

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


class GoogleSheetsError(RuntimeError):
    """Sanitized Google API failure."""


class GoogleSheetsClient:
    """Bound client for one configured publication spreadsheet."""

    def __init__(self, spreadsheet_id: str, service_account_file: Path) -> None:
        self.spreadsheet_id = spreadsheet_id
        self.credentials = Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            str(service_account_file), scopes=[SHEETS_SCOPE]
        )

    def _service(self) -> Any:
        return build("sheets", "v4", credentials=self.credentials, cache_discovery=False)

    async def health(self) -> dict[str, Any]:
        """Read only spreadsheet identity fields."""

        def request() -> dict[str, Any]:
            return cast(
                dict[str, Any],
                self._service()
                .spreadsheets()
                .get(spreadsheetId=self.spreadsheet_id, fields="spreadsheetId,properties.title")
                .execute(),
            )

        try:
            return await asyncio.to_thread(request)
        except Exception as exc:
            raise GoogleSheetsError("Google Sheets health check failed") from exc

    async def write_values(self, range_name: str, rows: list[list[object]]) -> dict[str, Any]:
        """Write materialized canonical values to one managed range."""

        def request() -> dict[str, Any]:
            return cast(
                dict[str, Any],
                self._service()
                .spreadsheets()
                .values()
                .update(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                    valueInputOption="RAW",
                    body={"values": rows},
                )
                .execute(),
            )

        try:
            return await asyncio.to_thread(request)
        except Exception as exc:
            raise GoogleSheetsError("Google Sheets publication failed") from exc
