"""Bring both databases to the current schema. Safe to run repeatedly.

    python -m graphy.scripts.init_db
"""

import logging
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from neo4j.exceptions import ServiceUnavailable

from graphy.db.neo4j import apply_schema
from graphy.db.postgres import sync_session
from graphy.services.analytics_rules import seed_default_rules

log = logging.getLogger("init_db")


def main() -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")

    command.upgrade(Config(str(Path(__file__).resolve().parents[2] / "alembic.ini")), "head")

    with sync_session() as pg:
        log.info("default analytics rules added: %d", seed_default_rules(pg))

    for attempt in range(30):  # Neo4j takes a while on first boot
        try:
            apply_schema()
            return
        except ServiceUnavailable:
            log.info("waiting for Neo4j (%d/30)", attempt + 1)
            time.sleep(2)
    raise SystemExit("Neo4j did not become available")


if __name__ == "__main__":
    main()
