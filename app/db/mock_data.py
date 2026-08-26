# File: app/db/mock_data.py
"""Synthetic SAP and GIS address data generator.

Generates realistic Indian canonical addresses with SAP premise IDs and produces
8 distinct permutation variations for each address for benchmarking and testing.
Saves canonical records to DuckDB and permutations to JSON fixtures.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import TypedDict

import click
import duckdb

from app.models.address import AddressSlots, CanonicalAddress


class Locality(TypedDict):
    """Structure of an Indian locality with city, state, pincodes, and streets."""

    state: str
    state_code: str
    city: str
    pincodes: list[str]
    streets: list[str]
    landmarks: list[str]


# Real Indian cities, states, and pincode prefix mappings
INDIAN_LOCALITIES: list[Locality] = [
    {
        "state": "Bihar",
        "state_code": "BR",
        "city": "Patna",
        "pincodes": ["800001", "800002", "800003", "800004", "800020"],
        "streets": [
            "Mahatma Gandhi Road",
            "Boring Road",
            "Bailey Road",
            "Frazer Road",
            "Kankarbagh Main Road",
            "Ashok Rajpath",
            "Danapur Main Road",
        ],
        "landmarks": ["Near Gandhi Maidan", "Opposite Patna Museum", "Near Dak Bungalow"],
    },
    {
        "state": "Maharashtra",
        "state_code": "MH",
        "city": "Mumbai",
        "pincodes": ["400001", "400050", "400053", "400076", "400092"],
        "streets": [
            "Linking Road",
            "Swami Vivekananda Road",
            "Dr Dadabhai Naoroji Road",
            "Mahatma Gandhi Road",
            "Senapati Bapat Marg",
            "Lal Bahadur Shastri Marg",
        ],
        "landmarks": ["Near Bandra Station", "Opposite Phoenix Mall", "Near Powai Lake"],
    },
    {
        "state": "Karnataka",
        "state_code": "KA",
        "city": "Bengaluru",
        "pincodes": ["560001", "560034", "560038", "560068", "560100"],
        "streets": [
            "Mahatma Gandhi Road",
            "Brigade Road",
            "100 Feet Road Indiranagar",
            "Outer Ring Road",
            "Hosur Road",
            "Bannerghatta Main Road",
        ],
        "landmarks": ["Near Trinity Circle", "Opposite Forum Mall", "Near Silk Board"],
    },
    {
        "state": "Delhi",
        "state_code": "DL",
        "city": "New Delhi",
        "pincodes": ["110001", "110016", "110020", "110075", "110092"],
        "streets": [
            "Barakhamba Road",
            "Connaught Circus",
            "Ring Road",
            "Vikas Marg",
            "Aurobindo Marg",
            "Nelson Mandela Marg",
        ],
        "landmarks": ["Near India Gate", "Opposite AIIMS", "Near Connaught Place"],
    },
    {
        "state": "West Bengal",
        "state_code": "WB",
        "city": "Kolkata",
        "pincodes": ["700001", "700019", "700029", "700064", "700091"],
        "streets": [
            "Park Street",
            "Jawaharlal Nehru Road",
            "Rashbehari Avenue",
            "EM Bypass",
            "Bidhan Sarani",
            "Strand Road",
        ],
        "landmarks": ["Near Victoria Memorial", "Opposite South City Mall", "Near Salt Lake"],
    },
    {
        "state": "Tamil Nadu",
        "state_code": "TN",
        "city": "Chennai",
        "pincodes": ["600001", "600017", "600028", "600034", "600086"],
        "streets": [
            "Anna Salai",
            "Poonamallee High Road",
            "Mahatma Gandhi Road",
            "Cathedral Road",
            "Rajiv Gandhi Salai",
        ],
        "landmarks": ["Near Central Station", "Opposite Express Avenue", "Near Marina Beach"],
    },
]

SOURCE_DATABASES = ["SAP_HANA", "GIS_POSTGIS", "BILLING_ORACLE"]
FLAT_LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H"]


def generate_canonical_address(rng: random.Random) -> CanonicalAddress:
    """Generate a single random canonical address record.

    Args:
        rng: Seeded random instance for deterministic generation.

    Returns:
        CanonicalAddress: Validated canonical address model.
    """
    loc = rng.choice(INDIAN_LOCALITIES)
    state = loc["state"]
    city = loc["city"]
    pincode = rng.choice(loc["pincodes"])
    street = rng.choice(loc["streets"])
    landmark = rng.choice(loc["landmarks"])

    premise_num = str(rng.randint(1, 500))
    floor_num = rng.randint(1, 25)
    flat_letter = rng.choice(FLAT_LETTERS)
    flat_no = f"{floor_num}{flat_letter}"

    sap_premise_id = f"PR-{pincode}-{premise_num}-{flat_no}"
    full_address = f"{premise_num} {street}, Flat {flat_no}, {city}, {state} {pincode}, India"

    # Normalized tokens representation
    tokens = [
        t.lower().replace(",", "").replace(".", "").strip()
        for t in full_address.split()
        if t.strip()
    ]
    normalized_tokens = sorted(set(tokens))

    slots = AddressSlots(
        raw_input=full_address,
        pincode=pincode,
        pincode_missing=False,
        premise_number=premise_num,
        flat_no=flat_no.lower(),
        street=street.lower(),
        landmark=landmark.lower(),
        city=city.lower(),
        state=state.lower(),
        country="india",
        normalized_tokens=normalized_tokens,
    )

    return CanonicalAddress(
        sap_premise_id=sap_premise_id,
        full_address=full_address,
        slots=slots,
        embedding=None,
        geohash=f"h3_r7_{rng.randint(1000, 9999)}",
        source_db=rng.choice(SOURCE_DATABASES),
    )


def generate_permutations(canonical: CanonicalAddress) -> list[dict[str, str]]:
    """Generate the 8 canonical test permutations for an address.

    Args:
        canonical: The source canonical address record.

    Returns:
        list[dict[str, str]]: List of 8 permutation dicts with label, input, and expected ID.
    """
    s = canonical.slots
    premise = s.premise_number or "1"
    flat = (s.flat_no or "1a").upper()
    street = s.street or "road"
    city = (s.city or "city").title()
    state = (s.state or "state").title()
    pin = s.pincode or "110001"
    sap_id = canonical.sap_premise_id

    # Street short form
    street_abbrev = (
        street.replace("mahatma gandhi road", "MG Rd")
        .replace("jawaharlal nehru road", "JL Nehru Rd")
        .replace("road", "Rd")
        .replace("marg", "Marg")
        .replace("salai", "Salai")
    )

    return [
        {
            "type": "p1_canonical",
            "input": f"{premise} {street.title()}, Flat {flat}, {city}, {state} {pin}, India",
            "expected_sap_id": sap_id,
        },
        {
            "type": "p2_abbreviated",
            "input": f"#{flat}, {premise}, {street_abbrev}, {city} ({pin})",
            "expected_sap_id": sap_id,
        },
        {
            "type": "p3_jumbled_order",
            "input": f"Flat {flat}, {premise} {street_abbrev}, {pin} {city}, {state}, India",
            "expected_sap_id": sap_id,
        },
        {
            "type": "p4_prefix_flat",
            "input": f"{flat} - {premise} {street_abbrev}, {city} {pin}, {state}, India",
            "expected_sap_id": sap_id,
        },
        {
            "type": "p5_compact_slash",
            "input": f"{premise}/{flat} {street_abbrev}, {city}-{pin}",
            "expected_sap_id": sap_id,
        },
        {
            "type": "p6_state_country_code",
            "input": f"{premise} {street_abbrev}, #{flat}, {city}, {state[:2].upper()} {pin}, IN",
            "expected_sap_id": sap_id,
        },
        {
            "type": "p7_missing_pincode",
            "input": (
                f"Flat {flat}, {premise} {street.title()}, {s.landmark or ''}, {city}, {state}"
            ),
            "expected_sap_id": sap_id,
        },
        {
            "type": "p8_phonetic_typo",
            "input": (
                f"{premise} {street_abbrev.replace('MG', 'Mahatama Gandhi')}, "
                f"Flat {flat}, {city} {pin}"
            ),
            "expected_sap_id": sap_id,
        },
    ]


def generate_canonical_dataset(records: int = 1000, seed: int = 42) -> list[CanonicalAddress]:
    """Generate a deterministic list of unique CanonicalAddress objects.

    Args:
        records: Total count of canonical addresses to generate.
        seed: Random seed.

    Returns:
        list[CanonicalAddress]: Generated canonical address models.
    """
    rng = random.Random(seed)
    canonical_list: list[CanonicalAddress] = []
    seen_ids: set[str] = set()

    while len(canonical_list) < records:
        addr = generate_canonical_address(rng)
        if addr.sap_premise_id in seen_ids:
            continue
        seen_ids.add(addr.sap_premise_id)
        canonical_list.append(addr)

    return canonical_list


def init_duckdb_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Initialize DuckDB table and search indices.

    Args:
        conn: DuckDB connection object.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS addresses (
            sap_premise_id   VARCHAR PRIMARY KEY,
            full_address     VARCHAR NOT NULL,
            pincode          VARCHAR(6),
            premise_number   VARCHAR,
            flat_no          VARCHAR,
            street           VARCHAR,
            city             VARCHAR,
            state            VARCHAR,
            normalized_str   VARCHAR,
            embedding        FLOAT[768],
            geohash          VARCHAR,
            source_db        VARCHAR,
            created_at       TIMESTAMP,
            updated_at       TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_pincode ON addresses(pincode);
        CREATE INDEX IF NOT EXISTS idx_premise ON addresses(pincode, premise_number, flat_no);
        """
    )


def insert_canonical_addresses(
    conn: duckdb.DuckDBPyConnection, addresses: list[CanonicalAddress]
) -> None:
    """Insert a list of canonical address records into DuckDB.

    Args:
        conn: DuckDB connection object.
        addresses: List of CanonicalAddress objects to insert.
    """
    init_duckdb_schema(conn)

    rows = [
        (
            addr.sap_premise_id,
            addr.full_address,
            addr.slots.pincode,
            addr.slots.premise_number,
            addr.slots.flat_no,
            addr.slots.street,
            addr.slots.city,
            addr.slots.state,
            " ".join(addr.slots.normalized_tokens),
            addr.embedding,
            addr.geohash,
            addr.source_db,
            addr.created_at,
            addr.updated_at,
        )
        for addr in addresses
    ]

    conn.executemany(
        """
        INSERT OR REPLACE INTO addresses (
            sap_premise_id, full_address, pincode, premise_number,
            flat_no, street, city, state, normalized_str,
            embedding, geohash, source_db, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


@click.command()
@click.option("--records", default=1000, help="Number of canonical records to generate.")
@click.option("--seed", default=42, help="Random seed for deterministic generation.")
@click.option("--db-path", default="./data/addresses.db", help="Path to DuckDB database file.")
@click.option(
    "--fixtures-path",
    default="./tests/fixtures/permutations.json",
    help="Path to permutations output file.",
)
@click.option("--clean", is_flag=True, default=True, help="Clean existing DB before seeding.")
def generate_data(records: int, seed: int, db_path: str, fixtures_path: str, clean: bool) -> None:
    """CLI entrypoint to generate synthetic SAP dataset and test fixtures.

    Args:
        records: Total count of canonical addresses.
        seed: Deterministic integer seed.
        db_path: Target DuckDB database path.
        fixtures_path: Target JSON fixtures path.
        clean: Whether to delete existing database file before seeding.
    """
    rng = random.Random(seed)
    click.echo(f"Generating {records} canonical records with seed={seed}...")

    canonical_list: list[CanonicalAddress] = []
    seen_ids: set[str] = set()
    all_permutations: list[dict[str, str]] = []

    while len(canonical_list) < records:
        addr = generate_canonical_address(rng)
        if addr.sap_premise_id in seen_ids:
            continue
        seen_ids.add(addr.sap_premise_id)
        canonical_list.append(addr)
        all_permutations.extend(generate_permutations(addr))

    # Ensure parent directories exist
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    if clean and db_file.exists():
        db_file.unlink()

    fix_file = Path(fixtures_path)
    fix_file.parent.mkdir(parents=True, exist_ok=True)

    # Save to DuckDB
    conn = duckdb.connect(db_path)
    insert_canonical_addresses(conn, canonical_list)
    conn.close()
    click.echo(f"Saved {len(canonical_list)} records to DuckDB at {db_path}")

    # Save permutations to JSON
    with open(fix_file, "w", encoding="utf-8") as f:
        json.dump(all_permutations, f, indent=2, ensure_ascii=False)
    click.echo(f"Saved {len(all_permutations)} permutations to {fixtures_path}")


if __name__ == "__main__":
    generate_data()
