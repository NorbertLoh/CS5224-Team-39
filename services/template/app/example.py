"""CLI transaction example; no unauthenticated example write endpoint is exposed."""

import argparse

from sqlalchemy import select

from app.database import Database
from app.models import ExampleItem
from app.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Insert a synthetic example item and read it back")
    parser.add_argument("--name", default="demo-item")
    args = parser.parse_args()
    if not 1 <= len(args.name) <= 100:
        parser.error("name must contain 1-100 characters")
    database = Database(Settings())
    try:
        with database.sessions.begin() as session:
            item = session.scalar(select(ExampleItem).where(ExampleItem.name == args.name))
            if item is None:
                item = ExampleItem(name=args.name)
                session.add(item)
                session.flush()
            item_id = item.id
        with database.sessions() as session:
            stored = session.get(ExampleItem, item_id)
            print(f"Example item persisted: {stored.id}")
    finally:
        database.close()


if __name__ == "__main__":
    main()
