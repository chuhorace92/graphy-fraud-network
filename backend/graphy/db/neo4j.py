"""Neo4j drivers and schema (TRD section 3)."""

import logging
from collections.abc import AsyncIterator
from functools import lru_cache

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession, Driver, GraphDatabase

from graphy.config import get_settings

log = logging.getLogger(__name__)

SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT source_record_id IF NOT EXISTS "
    "FOR (n:SourceRecord) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT attribute_value_id IF NOT EXISTS "
    "FOR (n:AttributeValue) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE",
    "CREATE CONSTRAINT group_id IF NOT EXISTS FOR (n:Group) REQUIRE n.group_id IS UNIQUE",
    "CREATE CONSTRAINT cluster_id IF NOT EXISTS FOR (n:Cluster) REQUIRE n.cluster_id IS UNIQUE",
    "CREATE INDEX attribute_value_type_normalized IF NOT EXISTS "
    "FOR (n:AttributeValue) ON (n.attr_type, n.normalized)",
    "CREATE INDEX attribute_value_hash IF NOT EXISTS FOR (n:AttributeValue) ON (n.hash)",
    "CREATE INDEX entity_type IF NOT EXISTS FOR (n:Entity) ON (n.entity_type)",
    "CREATE INDEX source_record_entity_type IF NOT EXISTS "
    "FOR (n:SourceRecord) ON (n.entity_type)",
    "CREATE INDEX cluster_run IF NOT EXISTS FOR (n:Cluster) ON (n.run_id)",
    "CREATE FULLTEXT INDEX entity_search IF NOT EXISTS "
    "FOR (n:Entity) ON EACH [n.canonical_name]",
    # Only `display` is indexed: secret attributes keep a masked display and no raw value.
    "CREATE FULLTEXT INDEX attribute_search IF NOT EXISTS "
    "FOR (n:AttributeValue) ON EACH [n.display]",
]


@lru_cache
def async_driver() -> AsyncDriver:
    s = get_settings()
    return AsyncGraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))


@lru_cache
def sync_driver() -> Driver:
    s = get_settings()
    return GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))


async def get_graph() -> AsyncIterator[AsyncSession]:
    async with async_driver().session(database=get_settings().neo4j_database) as session:
        yield session


def apply_schema() -> None:
    with sync_driver().session(database=get_settings().neo4j_database) as session:
        for statement in SCHEMA_STATEMENTS:
            session.run(statement)
    log.info("Neo4j schema applied (%d statements)", len(SCHEMA_STATEMENTS))
