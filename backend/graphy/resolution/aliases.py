"""Entity-level links derived after resolution: roles (RELATED_TO).

Probable aliases (ALIAS_OF) used to be found here; they now come out of the same scoring that
merges records, as the pairs that score in the review band (resolution.deterministic).
"""

import logging

from neo4j import Driver

from graphy.config import Settings

log = logging.getLogger(__name__)


def rebuild_related(*, driver: Driver, settings: Settings) -> int:
    """Lift record-level REL edges onto resolved entities as RELATED_TO."""
    with driver.session(database=settings.neo4j_database) as session:
        session.run("MATCH ()-[x:RELATED_TO]->() DELETE x").consume()
        summary = session.run(
            """
            MATCH (a:SourceRecord)-[x:REL]->(b:SourceRecord),
                  (a)-[:RESOLVED_TO]->(ea:Entity), (b)-[:RESOLVED_TO]->(eb:Entity)
            WHERE ea <> eb
            WITH ea, eb, x.rel_type AS rel_type, min(x.first_seen) AS first_seen,
                 max(x.last_seen) AS last_seen
            CREATE (ea)-[:RELATED_TO {rel_type: rel_type, first_seen: first_seen,
                                      last_seen: last_seen}]->(eb)
            """).consume()
    return summary.counters.relationships_created
