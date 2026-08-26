# File: app/db/multi_db_federator.py
"""Multi-database federator and CDC ingestion connectors.

Provides connector abstractions for SAP S/4HANA, PostGIS GIS, and Oracle RDBMS
billing sources, handling change data capture (CDC) ingestion and schema mapping.
"""

from __future__ import annotations

import datetime
from typing import Any

from app.engines.normalizer import normalize
from app.models.address import CanonicalAddress


class MultiDBFederator:
    """Federates address data streams from SAP S/4HANA, PostGIS, and Oracle."""

    def __init__(self) -> None:
        """Initialize database connection handlers."""
        self.connected_sources = ["SAP_S4HANA", "GIS_POSTGIS", "ORACLE_BILLING"]

    def ingest_cdc_event(self, source: str, raw_payload: dict[str, Any]) -> CanonicalAddress:
        """Transform inbound CDC event payload from any source into a CanonicalAddress.

        Args:
            source: Source database identifier (e.g. "SAP_S4HANA").
            raw_payload: Raw JSON event payload from Kafka/Debezium.

        Returns:
            CanonicalAddress: Standardized canonical record.
        """
        raw_address = str(raw_payload.get("address_text") or raw_payload.get("full_address", ""))
        slots = normalize(raw_address)

        premise_no = slots.premise_number or "0"
        flat_no = slots.flat_no or "0"
        pincode = slots.pincode or "000000"

        sap_id = str(
            raw_payload.get("sap_premise_id")
            or f"PR-{pincode}-{premise_no.upper()}-{flat_no.upper()}"
        )

        now = datetime.datetime.now(datetime.UTC)
        return CanonicalAddress(
            sap_premise_id=sap_id,
            full_address=raw_address,
            slots=slots,
            geohash=raw_payload.get("geohash"),
            source_db=source,
            created_at=now,
            updated_at=now,
        )

    def verify_checksum(self, record_a: CanonicalAddress, record_b: CanonicalAddress) -> bool:
        """Verify checksum equality between source record and DuckDB index.

        Args:
            record_a: First CanonicalAddress instance.
            record_b: Second CanonicalAddress instance.

        Returns:
            bool: True if slots and premise IDs are identical.
        """
        return (
            record_a.sap_premise_id == record_b.sap_premise_id
            and record_a.slots.model_dump() == record_b.slots.model_dump()
        )
