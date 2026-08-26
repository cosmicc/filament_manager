"""Safe identifiers and serialization for printer-side spool preflight."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

MAX_CATALOG_SPOOLS = 250
MAX_CANDIDATES_PER_MATERIAL = 24
MAX_PROMPT_LABEL_LENGTH = 96
CATALOG_REVISION_PATTERN = re.compile(r"[0-9a-f]{64}")
PROMPT_LABEL_SEPARATOR_PATTERN = re.compile(r"[^A-Za-z0-9._#-]+")


class SpoolPreflightError(RuntimeError):
    """Raised when a safe printer-side spool catalog cannot be produced."""


@dataclass(frozen=True, slots=True)
class SpoolPreflightCatalog:
    """Bounded print choices, manual choices, and safe load temperatures."""

    materials: dict[str, list[list[int | str]]]
    manual_spools: list[list[int | str]]
    print_temperatures: dict[str, str]
    temperatures: dict[str, str]
    revision: str

    def materials_literal(self) -> str:
        """Return a compact Python-compatible literal for Klipper."""

        return _compact_literal(self.materials)

    def temperatures_literal(self) -> str:
        """Return a compact Python-compatible literal for Klipper."""

        return _compact_literal(self.temperatures)

    def print_temperatures_literal(self) -> str:
        """Return published Cura-profile load temperatures for Klipper."""

        return _compact_literal(self.print_temperatures)

    def manual_spools_literal(self) -> str:
        """Return the bounded manual-load choices as a Klipper literal."""

        return _compact_literal(self.manual_spools)


def cura_material_guid(source_kind: str, source_id: UUID | str) -> str:
    """Return the deterministic GUID written into one managed Cura material."""

    if source_kind not in {"product", "template"}:
        raise ValueError("unsupported Cura material source kind")
    parsed_id = UUID(str(source_id))
    return str(uuid5(NAMESPACE_URL, f"filament-manager-{source_kind}:{parsed_id}"))


def cura_product_scope_id(
    filament_product_id: UUID | str,
    printer_id: UUID | str,
    nozzle_diameter_mm: Decimal | str,
) -> UUID:
    """Return the stable identity for one product, printer, and nozzle scope.

    Material-profile rows are immutable snapshots, so their database IDs change
    after every edit. Cura container stacks must instead reference an identity
    that remains stable for the semantic scope represented by those snapshots.
    """

    product_id = UUID(str(filament_product_id))
    parsed_printer_id = UUID(str(printer_id))
    diameter = Decimal(str(nozzle_diameter_mm))
    if not diameter.is_finite() or diameter <= 0:
        raise ValueError("Cura material scope requires a positive nozzle diameter")
    normalized_diameter = format(diameter.normalize(), "f")
    return uuid5(
        NAMESPACE_URL,
        f"filament-manager-product-scope:{product_id}:{parsed_printer_id}:{normalized_diameter}",
    )


def cura_product_material_guid(
    filament_product_id: UUID | str,
    printer_id: UUID | str,
    nozzle_diameter_mm: Decimal | str,
) -> str:
    """Return the stable Cura GUID for one managed product profile scope."""

    return cura_material_guid(
        "product",
        cura_product_scope_id(filament_product_id, printer_id, nozzle_diameter_mm),
    )


def spool_prompt_label(*parts: object) -> str:
    """Create a bounded, command-safe label for a Fluidd prompt button."""

    normalized_parts: list[str] = []
    for part in parts:
        value = unicodedata.normalize("NFKD", str(part)).encode("ascii", "ignore").decode("ascii")
        value = PROMPT_LABEL_SEPARATOR_PATTERN.sub("-", value).strip("-._")
        if value:
            normalized_parts.append(value)
    label = "-".join(normalized_parts)[:MAX_PROMPT_LABEL_LENGTH].rstrip("-._")
    if not label:
        raise ValueError("spool prompt label contains no safe characters")
    return label


def build_catalog_revision(
    materials: dict[str, list[list[int | str]]],
    manual_spools: list[list[int | str]],
    print_temperatures: dict[str, str],
    temperatures: dict[str, str],
) -> str:
    """Hash the complete printer catalog for drift detection."""

    payload = {
        "manual_spools": manual_spools,
        "materials": materials,
        "print_temperatures": print_temperatures,
        "temperatures": temperatures,
    }
    return hashlib.sha256(_compact_literal(payload).encode("ascii")).hexdigest()


def validate_catalog_revision(value: str) -> str:
    """Reject values that cannot be safely embedded as a Klipper string."""

    if CATALOG_REVISION_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid spool catalog revision")
    return value


def _compact_literal(value: object) -> str:
    """Serialize bounded scalar containers without command-separating whitespace."""

    serialized = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    if "\n" in serialized or "\r" in serialized:
        raise ValueError("spool catalog contains a line break")
    return serialized
