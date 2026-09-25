"""Seeder for the supplier directory.

Loads the initial suppliers (``suppliers/seed_data.py``, from the supplier
CONTEXT) into TinyDB, validating each one through the Pydantic model first.

    python seed.py            # seed only if the database is empty
    python seed.py --reset    # wipe the database and reload the initial data

The API also calls ``seed_database`` on startup, so it never boots empty.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from tinydb import TinyDB

from core.config import get_suppliers_db_path
from suppliers.schemas import SupplierCreate
from suppliers.seed_data import SUPPLIERS_SEED


def seed_database(db: TinyDB, *, reset: bool = False) -> int:
    """Insert the initial suppliers. Returns how many were inserted."""
    if reset:
        db.truncate()
    elif len(db) > 0:
        return 0

    timestamp = datetime.now(timezone.utc).isoformat()
    for entry in SUPPLIERS_SEED:
        supplier = SupplierCreate(**entry)
        db.insert({**supplier.model_dump(mode="json"), "updated_at": timestamp})
    return len(SUPPLIERS_SEED)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the supplier directory into TinyDB.")
    parser.add_argument("--reset", action="store_true", help="wipe existing data before seeding")
    args = parser.parse_args()

    path = get_suppliers_db_path()
    with TinyDB(path) as db:
        inserted = seed_database(db, reset=args.reset)
        total = len(db)

    if inserted:
        print(f"Seeded {inserted} suppliers into {path}")
    else:
        print(f"Database already has {total} suppliers; nothing to do (use --reset to reload).")


if __name__ == "__main__":
    main()
