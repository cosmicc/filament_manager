"""Exact arithmetic and safety bounds for shared filament projection defaults."""

from decimal import Decimal

import pytest

from filament_manager.services.filament_defaults import ProductCostBasis, _spoolman_temperature


def test_scaled_product_price_does_not_round_through_a_kilogram_price() -> None:
    basis = ProductCostBasis(Decimal("1") / Decimal("3000"), "USD", 1)
    assert basis.price_for_weight(Decimal("1000")) == Decimal("0.33")
    assert basis.price_for_weight(Decimal("3000")) == Decimal("1.00")


@pytest.mark.parametrize(
    ("value", "maximum", "expected"),
    [
        ("0", 200, 0),
        ("60.4", 200, 60),
        ("215.5", 500, 216),
        ("-1", 500, None),
        ("201", 200, None),
        ("501", 500, None),
        ("NaN", 500, None),
        ("Infinity", 500, None),
    ],
)
def test_spoolman_temperature_is_bounded_and_whole_degrees(
    value: str,
    maximum: int,
    expected: int | None,
) -> None:
    assert _spoolman_temperature(Decimal(value), maximum) == expected


@pytest.mark.integration
@pytest.mark.asyncio
async def test_manufacturer_tare_uses_mode_exact_capacity_and_archived_evidence() -> None:
    """Share packaging evidence, never physical weights or unknown manufacturers."""

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from testcontainers.community.postgres import PostgresContainer

    from filament_manager.models import Base
    from filament_manager.models.inventory import FilamentProduct, Spool, Vendor
    from filament_manager.services.filament_defaults import spoolman_filament_defaults

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        engine = create_async_engine(postgres.get_connection_url())
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            vendor, unknown = Vendor(name="Maker"), Vendor(name="Unknown")
            session.add_all([vendor, unknown])
            await session.flush()
            products = [
                FilamentProduct(
                    vendor_id=manufacturer.id,
                    material_type="PLA",
                    product_name=f"Product {index}",
                    color_name="Black",
                    color_hex="000000",
                    diameter_mm=Decimal("1.75"),
                    density_g_cm3=Decimal("1.24"),
                    nominal_net_mass_g=Decimal("1000"),
                )
                for index, manufacturer in enumerate((vendor, vendor, unknown))
            ]
            session.add_all(products)
            await session.flush()
            spools = [
                Spool(
                    spool_code=f"TEST-{index}",
                    filament_product_id=products[product_index].id,
                    tare_mass_g=Decimal(tare),
                    nominal_net_mass_g=Decimal(capacity),
                    remaining_mass_expected_g=Decimal("100"),
                    remaining_mass_effective_g=Decimal("100"),
                    archived=archived,
                )
                for index, (product_index, tare, capacity, archived) in enumerate(
                    [
                        (0, "210", "1000", True),
                        (0, "210", "1000", False),
                        (1, "180", "1000", False),
                        (1, "90", "250", False),
                        (2, "999", "1000", False),
                    ]
                )
            ]
            session.add_all(spools)
            await session.flush()
            result = await spoolman_filament_defaults(session, products, printer_code=None)
            assert [result[p.id]["spool_weight"] for p in products] == [210, 210, None]
            spools[0].tare_mass_g = Decimal("180")
            await session.flush()
            result = await spoolman_filament_defaults(session, products, printer_code=None)
            assert result[products[0].id]["spool_weight"] == 180
            spools[0].tare_mass_g = Decimal("0")
            products[1].nominal_net_mass_g = Decimal("250")
            await session.flush()
            result = await spoolman_filament_defaults(session, products, printer_code=None)
            assert result[products[0].id]["spool_weight"] == 180  # Lower tare breaks a 1:1 tie.
            assert result[products[1].id]["spool_weight"] == 90
            assert spools[1].tare_mass_g == Decimal("210")
            assert spools[1].remaining_mass_effective_g == Decimal("100")
        await engine.dispose()
