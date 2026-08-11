"""Supplied master-workbook validation tests."""

from pathlib import Path

from filament_manager.services.workbook_import import analyze_workbook

WORKBOOK = Path(__file__).parents[1] / "reference" / "Filament Inventory Master.xlsx"


def test_supplied_workbook_matches_import_contract() -> None:
    report = analyze_workbook(WORKBOOK)
    assert report["inventory_columns"] == 34
    assert report["populated_rows"] == 35
    assert report["valid_rows"] == 35
    assert report["invalid_rows"] == 0


def test_supplied_workbook_has_unique_corrected_spool_codes() -> None:
    report_rows = analyze_workbook(WORKBOOK)["rows"]
    codes = [row["spool_code"] for row in report_rows]
    assert len(codes) == len(set(codes))
    assert "P11" in codes
    assert "P11-S" in codes


def test_workbook_report_can_keep_uploaded_source_name(tmp_path: Path) -> None:
    uploaded = tmp_path / "stored-upload.xlsx"
    uploaded.write_bytes(WORKBOOK.read_bytes())

    report = analyze_workbook(uploaded, source_name="Master Upload.xlsx")

    assert report["source"] == "Master Upload.xlsx"
    assert report["sha256"] == analyze_workbook(WORKBOOK)["sha256"]
