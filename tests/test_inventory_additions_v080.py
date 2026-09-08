"""Immutable automatic spool codes and conservative printer preflight checks."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from test_build_plate_macros import ENVIRONMENT, MACROS, printer_snapshot, render
from test_build_plates import printer_config

from filament_manager.clients.moonraker import MoonrakerClient, MoonrakerError
from filament_manager.domain.extruders import extruder_name, tool_number
from filament_manager.services.spool_codes import next_spool_code


@pytest.mark.parametrize(
    "material,prefix",
    [
        ("PLA", "P"),
        ("PLA+", "P"),
        ("PETG", "G"),
        ("TPU", "T"),
        ("PP", "PP"),
        ("SPLA", "S"),
        ("ASA", "ASA"),
        ("ABS", "ABS"),
        ("PA", "PA"),
        ("PC", "PC"),
    ],
)
def test_next_code_fills_gaps_without_changing_existing_codes(material: str, prefix: str) -> None:
    codes = [f"{prefix.lower()}01", f"{prefix}3", "legacy-91", f"{prefix}20"]
    assert next_spool_code(material, codes) == f"{prefix}2"
    assert next_spool_code(material, []) == f"{prefix}1"


@pytest.mark.parametrize(
    "required,remaining,blocked", [(100, 99, True), (100, 100, False), (100, 101, False), (-1, 100, True)]
)
def test_filament_gate_has_no_margin_and_requires_explicit_override(
    required: int, remaining: int, blocked: bool
) -> None:
    printer = printer_snapshot()
    state = printer["gcode_macro FILAMENT_MANAGER_SPOOL_STATE"]
    state.update(phase="checking_weight", start_pending=1, loaded_spool_id=12, weight_sequence=7)
    result = render(
        "FILAMENT_MANAGER_FILAMENT_CHECK",
        printer,
        ID="12",
        SEQUENCE="7",
        REQUIRED=str(required),
        REMAINING=str(remaining),
    )
    assert ("Override and Continue" in result) is blocked
    assert ("_FILAMENT_MANAGER_CONTINUE_START" in result) is not blocked
    if blocked:
        assert "Cancel Print|FILAMENT_MANAGER_ABORT" in result
    assert not render(
        "FILAMENT_MANAGER_FILAMENT_CHECK", printer, ID="12", SEQUENCE="6", REQUIRED="10", REMAINING="100"
    ).strip()
    assert not render("_FILAMENT_MANAGER_OVERRIDE_WEIGHT", printer, SEQUENCE="7").strip()
    state["phase"] = "insufficient_filament"
    assert "_FILAMENT_MANAGER_CONTINUE_START" in render(
        "_FILAMENT_MANAGER_OVERRIDE_WEIGHT", printer, SEQUENCE="7"
    )
    assert not render("_FILAMENT_MANAGER_OVERRIDE_WEIGHT", printer, SEQUENCE="6").strip()


@pytest.mark.asyncio
@pytest.mark.parametrize("power", ["off", "on", "error", "init", None])
async def test_power_off_requires_positive_switch_evidence(power: str | None) -> None:
    client = MoonrakerClient(printer_config())
    client._get = AsyncMock(side_effect=[{"result": {"state": "shutdown"}}, {"result": {"printer": power}}])
    result = await client.operational_state()
    assert result.power_state == power
    assert client._get.await_count == 2


@pytest.mark.asyncio
async def test_unreachable_printer_and_power_is_not_reported_off() -> None:
    client = MoonrakerClient(printer_config())
    client._get = AsyncMock(side_effect=MoonrakerError("unavailable"))
    with pytest.raises(MoonrakerError):
        await client.operational_state()


def test_hotend_selection_never_guesses_a_multi_hotend_target() -> None:
    assert extruder_name(None, 1) == "extruder"
    assert tool_number(extruder_name("extruder1", 2)) == 1
    for value in (None, "extruder2", "T1;G28", 1):
        with pytest.raises(ValueError):
            extruder_name(value, 2)


def test_tool_load_uses_existing_motion_and_verifies_selected_hotend() -> None:
    printer = printer_snapshot()
    printer.update(extruder={}, extruder1={})
    printer["gcode_macro T1"] = {}
    output = render("FILAMENT_MANAGER_TOOL_LOAD", printer, TOOL="1", ID="12", TEMP="210")
    assert output.index("T1") < output.index("FILAMENT_MANAGER_TOOL_CHANGED EXPECTED=extruder1")
    assert output.index("FILAMENT_MANAGER_TOOL_CHANGED") < output.index("FILAMENT_MANAGER_CHANGE_SPOOL")
    assert "ACTIVATE_EXTRUDER" not in output
    assert "G28" not in output
    printer["print_stats"]["state"] = "printing"
    with pytest.raises(ValueError, match="idle printer"):
        render("FILAMENT_MANAGER_TOOL_LOAD", printer, TOOL="1", ID="12", TEMP="210")


@pytest.mark.parametrize(
    "macro",
    [
        "_FILAMENT_MANAGER_BEGIN_CHANGE",
        "_FILAMENT_MANAGER_BEGIN_MANUAL_CHANGE",
        "_FILAMENT_MANAGER_PROMPT_INSERT",
        "_FILAMENT_MANAGER_LOAD_SELECTED",
    ],
)
def test_duplicate_hotend_spool_is_rejected_before_motion(macro: str) -> None:
    """Stale selections cannot unload or load a spool belonging to another tool."""
    printer = printer_snapshot()
    state = printer["gcode_macro FILAMENT_MANAGER_SPOOL_STATE"]
    state.update(loaded_spools={"extruder1": 12}, target_spool_id=12, target_temp=210, phase="inserting")
    with pytest.raises(ValueError, match="another hotend"):
        render(macro, printer)


@pytest.mark.parametrize(
    "macro",
    ["_FILAMENT_MANAGER_PROMPT_INSERT", "_FILAMENT_MANAGER_LOAD_SELECTED", "_FILAMENT_MANAGER_PURGE_MORE"],
)
def test_stale_insertion_cannot_move_a_different_hotend(macro: str) -> None:
    """A physical tool change invalidates insertion and purge confirmation."""
    printer = printer_snapshot()
    printer["toolhead"]["extruder"] = "extruder1"
    printer["gcode_macro FILAMENT_MANAGER_SPOOL_STATE"].update(workflow_tool="extruder", phase="inserting")
    with pytest.raises(ValueError):
        render(macro, printer)


def test_managed_print_cannot_apply_t0_material_to_another_hotend() -> None:
    """Position-zero Cura identity must not be treated as a different tool's material."""
    printer = printer_snapshot()
    printer["toolhead"]["extruder"] = "extruder1"
    printer["gcode_macro FILAMENT_MANAGER_SPOOL_STATE"].update(initialized=1, start_pending=1)
    with pytest.raises(ValueError, match="Select T0"):
        render("FILAMENT_MANAGER_START_PRINT", printer, MATERIAL_GUID="managed-guid")
    with pytest.raises(ValueError, match="Return to T0"):
        render("_FILAMENT_MANAGER_CONTINUE_START", printer)


def test_physical_commit_preserves_other_hotend_and_uses_selected_tool() -> None:
    printer = printer_snapshot()
    state = printer["gcode_macro FILAMENT_MANAGER_SPOOL_STATE"]
    state.update(loaded_spools={"extruder": 7}, loaded_temperatures={"extruder": 210})
    printer["toolhead"]["extruder"] = "extruder1"
    calls: list[object] = []

    def fail(message: str) -> None:
        raise ValueError(message)

    output = ENVIRONMENT.from_string(
        MACROS.get("gcode_macro _FILAMENT_MANAGER_RECORD_LOADED", "gcode")
    ).render(
        printer=printer,
        params={"ID": "12", "TEMP": "225"},
        action_raise_error=fail,
        action_call_remote_method=lambda method, **values: calls.append((method, values)) or "",
    )
    assert calls == [("spoolman_set_active_spool", {"spool_id": 12})]
    assert "{'extruder': 7, 'extruder1': 12}" in output
    assert "{'extruder': 210, 'extruder1': 225.0}" in output
    assert state["loaded_spools"] == {"extruder": 7}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_independent_spools_and_automatic_code_allocation() -> None:
    """Real PostgreSQL preserves each loaded slot and allocates around archives."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.community.postgres import PostgresContainer

    from filament_manager.models import Base
    from filament_manager.models.inventory import FilamentProduct, Printer, Spool
    from filament_manager.services.moonraker_sync import synchronize_active_spool
    from filament_manager.services.spool_codes import allocate_spool_code

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as database:
        engine = create_async_engine(database.get_connection_url())
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            printer = Printer(
                id=uuid4(),
                printer_code="multi",
                name="Multi",
                moonraker_base_url="http://printer.test",
                nozzle_diameter_mm=Decimal("0.4"),
                extruder_count=2,
            )
            product = FilamentProduct(
                id=uuid4(),
                material_type="PLA+",
                color_name="Blue",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
            )
            session.add_all([printer, product])
            await session.flush()
            spools = [
                Spool(
                    id=uuid4(),
                    spool_code=code,
                    filament_product_id=product.id,
                    nominal_net_mass_g=Decimal("1000"),
                    tare_mass_g=Decimal("200"),
                    remaining_mass_expected_g=Decimal("500"),
                    remaining_mass_effective_g=Decimal("500"),
                    spoolman_id=index + 1,
                    archived=index == 1,
                )
                for index, code in enumerate(["P1", "p03", "legacy-10"])
            ]
            session.add_all(spools)
            await session.commit()
            assert await allocate_spool_code(session, "PLA+") == "P2"
            await session.commit()
            for slot, spool in zip(("extruder", "extruder1"), (spools[0], spools[2]), strict=True):
                await synchronize_active_spool(
                    session,
                    printer_id=printer.id,
                    spoolman_id=spool.spoolman_id,
                    extruder=slot,
                    actor_id=None,
                    correlation_id="multi-test",
                )
            assert spools[0].active_printer_id == printer.id
            assert spools[2].active_printer_id == printer.id
            assert spools[2].active_extruder == "extruder1"
            with pytest.raises(ValueError, match="another hotend"):
                await synchronize_active_spool(
                    session,
                    printer_id=printer.id,
                    spoolman_id=spools[0].spoolman_id,
                    extruder="extruder1",
                    actor_id=None,
                    correlation_id="multi-test",
                )
            await synchronize_active_spool(
                session,
                printer_id=printer.id,
                spoolman_id=None,
                extruder="extruder1",
                actor_id=None,
                correlation_id="multi-test",
            )
            assert spools[0].active_printer_id == printer.id
            assert spools[2].active_printer_id is None

        async def create_numbered_spool() -> str:
            async with factory() as session:
                code = await allocate_spool_code(session, "PLA+")
                session.add(
                    Spool(
                        spool_code=code,
                        filament_product_id=product.id,
                        nominal_net_mass_g=Decimal("1000"),
                        tare_mass_g=Decimal("200"),
                        remaining_mass_expected_g=Decimal("1000"),
                        remaining_mass_effective_g=Decimal("1000"),
                    )
                )
                await session.commit()
                return code

        assert set(await asyncio.gather(create_numbered_spool(), create_numbered_spool())) == {"P2", "P4"}
        await engine.dispose()
