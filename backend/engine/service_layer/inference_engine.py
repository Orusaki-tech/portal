"""
Graph Inference Engine

Runs derived inference queries against the Neo4j knowledge graph to detect:
  - Compound hazards (multiple hazard types in same ward)
  - Chronic patterns (same hazard, same ward, frequent recurrence)
  - Catchment collapse (facility in flood zone, non-operational)
  - Pre-emptive alerts (similar wards to active ward have no signals)
  - Protection gaps (GBV signal, but no GBV service in county)
  - Policy gaps (active hazard has no matching policy for county)
  - Accountability chains (hazard → body → position → person)
  - Community detection (wards with similar PDI profiles)

Results are stored as new edges in Neo4j and events in PostgreSQL.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from backend.engine.adapters.neo4j_client import Neo4jClient
from backend.engine.domain.climate_events import (
    ChronicPatternDetected,
    CompoundHazardDetected,
    PolicyGapDetected,
)

logger = logging.getLogger(__name__)


class InferenceEngine:
    """
    Runs scheduled inference queries against the KG.

    Designed to be called:
      - On signal ingest (compound, catchment, pre-emptive)
      - On schedule / cron (chronic, policy gap, protection gap)
      - On demand via API
    """

    def __init__(self, neo4j: Neo4jClient, conn=None) -> None:
        self.neo4j = neo4j
        self.conn = conn

    # ── Compound Hazard Detection ───────────────────────────────────

    def detect_compound_hazards(self, county_code: str | None = None) -> list[dict[str, Any]]:
        """
        Find wards with multiple active signal hazard types.

        Returns list of {ward_pcode, hazard_types, signal_ids, risk_multiplier}
        """
        with self.neo4j.driver.session() as session:
            county_filter = "AND c.county_code = $county_code" if county_code else ""
            result = session.run(
                f"""
                MATCH (w:Ward)<-[:LOCATED_IN]-(s:Signal {{status: 'active'}})
                MATCH (w)-[:PART_OF]->(c:County)
                WITH w, c, collect(DISTINCT s.hazard_type) AS hazards, collect(s.id) AS signal_ids
                WHERE size(hazards) > 1
                {county_filter}
                RETURN w.pcode AS ward_pcode, w.name AS ward_name,
                       hazards, signal_ids, c.county_code AS county_code,
                       size(hazards) AS hazard_count
                ORDER BY hazard_count DESC
                """,
                county_code=county_code,
            )
            return [dict(r) for r in result]

    def create_compound_edges(self, results: list[dict[str, Any]]) -> None:
        """Store compound hazard detection as events."""
        for r in results:
            with self.neo4j.driver.session() as session:
                session.run(
                    """
                    MATCH (w:Ward {pcode: $pcode})
                    MERGE (w)-[:HAS_COMPOUND_HAZARD]->(w)
                    SET w.compound_hazards = $hazards,
                        w.last_compound_check = $timestamp
                    """,
                    pcode=r["ward_pcode"],
                    hazards=r["hazards"],
                    timestamp=datetime.now(UTC).isoformat(),
                )
            logger.info("Compound hazard in %s: %s", r["ward_pcode"], r["hazards"])

    # ── Chronic Pattern Detection ───────────────────────────────────

    def detect_chronic_patterns(
        self, hazard_type: str | None = None, threshold: int = 3, window_days: int = 180
    ) -> list[dict[str, Any]]:
        """
        Find wards with repeated signals of the same hazard type.

        Returns list of {ward_pcode, hazard_type, signal_count, first_seen, last_seen}
        """
        with self.neo4j.driver.session() as session:
            hazard_filter = "AND s.hazard_type = $hazard_type" if hazard_type else ""
            result = session.run(
                f"""
                MATCH (w:Ward)<-[:LOCATED_IN]-(s:Signal)
                WHERE s.timestamp > datetime() - duration('P{window_days}D')
                {hazard_filter}
                WITH w, s.hazard_type AS hazard, count(s) AS signal_count,
                     min(s.timestamp) AS first_seen, max(s.timestamp) AS last_seen
                WHERE signal_count >= $threshold
                RETURN w.pcode AS ward_pcode, w.name AS ward_name,
                       hazard, signal_count, first_seen, last_seen
                ORDER BY signal_count DESC
                """,
                hazard_type=hazard_type,
                threshold=threshold,
            )
            return [dict(r) for r in result]

    def create_chronic_edges(self, results: list[dict[str, Any]]) -> None:
        """Store chronic pattern as node property."""
        for r in results:
            with self.neo4j.driver.session() as session:
                session.run(
                    """
                    MATCH (w:Ward {pcode: $pcode})
                    SET w.chronic_hazards = COALESCE(w.chronic_hazards, {}) + $hazard_map,
                        w.last_chronic_check = $timestamp
                    """,
                    pcode=r["ward_pcode"],
                    hazard_map={r["hazard"]: r["signal_count"]},
                    timestamp=datetime.now(UTC).isoformat(),
                )
            logger.info("Chronic %s in %s: %d signals", r["hazard"], r["ward_pcode"], r["signal_count"])

    # ── Catchment Collapse Detection ────────────────────────────────

    def detect_catchment_collapse(self, county_code: str | None = None) -> list[dict[str, Any]]:
        """
        Find facilities that are:
          - Located in a ward with an active flood signal
          - Non-operational or lacking ambulance access
          - MISP stock below 50%

        Returns list of {facility_id, facility_name, ward_pcode, issues}
        """
        with self.neo4j.driver.session() as session:
            county_filter = "AND c.county_code = $county_code" if county_code else ""
            result = session.run(
                f"""
                MATCH (s:Signal {{status: 'active', hazard_type: 'flood'}})-[:LOCATED_IN]->(ward:Ward)
                MATCH (ward)-[:SERVED_BY]->(f:Facility)
                MATCH (ward)-[:PART_OF]->(c:County)
                {county_filter}
                WITH f, ward, c,
                     CASE WHEN f.operational = false THEN ['non_operational'] ELSE [] END AS issues,
                     CASE WHEN f.has_ambulance = false THEN ['no_ambulance'] ELSE [] END AS issues2,
                     CASE WHEN f.misp_stock_level < 50 THEN ['low_misp_stock'] ELSE [] END AS issues3
                WITH f, ward, c, issues + issues2 + issues3 AS all_issues
                WHERE size(all_issues) > 0
                RETURN f.id AS facility_id, f.name AS facility_name,
                       ward.pcode AS ward_pcode, ward.name AS ward_name,
                       c.county_code AS county_code,
                       all_issues, f.misp_stock_level AS misp_stock
                ORDER BY size(all_issues) DESC
                """,
                county_code=county_code,
            )
            return [dict(r) for r in result]

    def create_catchment_edges(self, results: list[dict[str, Any]]) -> None:
        """Store catchment collapse as edges."""
        for r in results:
            with self.neo4j.driver.session() as session:
                session.run(
                    """
                    MATCH (f:Facility {id: $facility_id})
                    SET f.catchment_issues = $issues,
                        f.catchment_checked_at = $timestamp
                    """,
                    facility_id=r["facility_id"],
                    issues=r["all_issues"],
                    timestamp=datetime.now(UTC).isoformat(),
                )

    # ── Pre-emptive Alert Detection ─────────────────────────────────

    def detect_preemptive_alerts(self, county_code: str | None = None) -> list[dict[str, Any]]:
        """
        Find wards that are SIMILAR_TO an active-signal ward but don't
        have any active signals themselves.

        Returns list of {active_ward_pcode, similar_ward_pcode, confidence, pop_wra}
        """
        with self.neo4j.driver.session() as session:
            county_filter = "AND ac.county_code = $county_code AND sc.county_code = $county_code" if county_code else ""
            result = session.run(
                f"""
                MATCH (wa:Ward)<-[:LOCATED_IN]-(:Signal {{status: 'active'}})
                MATCH (wa)-[sim:SIMILAR_TO]->(ws:Ward)
                MATCH (wa)-[:PART_OF]->(ac:County)
                MATCH (ws)-[:PART_OF]->(sc:County)
                WHERE NOT EXISTS {{
                    MATCH (ws)<-[:LOCATED_IN]-(:Signal {{status: 'active'}})
                }}
                {county_filter}
                RETURN wa.pcode AS active_ward_pcode, wa.name AS active_ward_name,
                       ws.pcode AS similar_ward_pcode, ws.name AS similar_ward_name,
                       sim.confidence AS similarity,
                       ws.pop_wra AS at_risk_pop_wra
                ORDER BY ws.pop_wra DESC
                LIMIT 20
                """,
                county_code=county_code,
            )
            return [dict(r) for r in result]

    def create_preemptive_edges(self, results: list[dict[str, Any]]) -> None:
        """Store pre-emptive alerts as edges."""
        for r in results:
            with self.neo4j.driver.session() as session:
                session.run(
                    """
                    MATCH (wa:Ward {pcode: $active_pcode})
                    MATCH (ws:Ward {pcode: $similar_pcode})
                    MERGE (wa)-[:ALERT_PREEMPTIVE {confidence: $confidence}]->(ws)
                    """,
                    active_pcode=r["active_ward_pcode"],
                    similar_pcode=r["similar_ward_pcode"],
                    confidence=r["similarity"],
                )
            logger.info("Pre-emptive: %s → %s", r["active_ward_pcode"], r["similar_ward_pcode"])

    # ── Protection Gap Detection ────────────────────────────────────

    def detect_protection_gaps(self, county_code: str | None = None) -> list[dict[str, Any]]:
        """
        Find counties where:
          - Active GBV signal exists
          - No GBV one-stop centre exists in the county

        Returns list of {county_code, hazard_type, signal_count, gbv_facility_count}
        """
        with self.neo4j.driver.session() as session:
            county_filter = "WHERE c.county_code = $county_code" if county_code else ""
            result = session.run(
                f"""
                MATCH (s:Signal {{status: 'active', hazard_type: 'GBV'}})-[:LOCATED_IN]->(:Ward)-[:PART_OF]->(c:County)
                OPTIONAL MATCH (gbv:GBVOneStop:Facility)-[:LOCATED_IN]->(:Ward)-[:PART_OF]->(c)
                {county_filter}
                WITH c, count(DISTINCT s) AS signal_count, count(DISTINCT gbv) AS gbv_facility_count
                WHERE gbv_facility_count = 0
                RETURN c.county_code AS county_code, c.name AS county_name,
                       signal_count, gbv_facility_count,
                       'GBV_PROTECTION_GAP' AS gap_type
                ORDER BY signal_count DESC
                """,
                county_code=county_code,
            )
            return [dict(r) for r in result]

    # ── Policy Gap Detection ────────────────────────────────────────

    def detect_policy_gaps(self, county_code: str | None = None) -> list[dict[str, Any]]:
        """
        Find active hazard types that have no matching policy for the county.

        Returns list of {county_code, hazard_type, signal_count}
        """
        with self.neo4j.driver.session() as session:
            county_filter = "WHERE c.county_code = $county_code" if county_code else ""
            result = session.run(
                f"""
                MATCH (s:Signal {{status: 'active'}})-[:LOCATED_IN]->(:Ward)-[:PART_OF]->(c:County)
                WITH c, s.hazard_type AS hazard, count(DISTINCT s) AS signal_count
                OPTIONAL MATCH (pc:PolicyChunk)-[:APPLICABLE_TO]->(h:Hazard {{name: hazard}})
                WHERE (pc)-[:APPLICABLE_TO]->(c)
                WITH c, hazard, signal_count, count(pc) AS policy_count
                {county_filter}
                WHERE policy_count = 0
                RETURN c.county_code AS county_code, c.name AS county_name,
                       hazard, signal_count, 'POLICY_GAP' AS gap_type
                ORDER BY signal_count DESC
                """,
                county_code=county_code,
            )
            return [dict(r) for r in result]

    # ── Accountability Chain ────────────────────────────────────────

    def get_accountability_chains(
        self, county_code: str, hazard_name: str
    ) -> list[dict[str, Any]]:
        """
        Trace full accountability: hazard → governing body → position → person → responsibility.

        Returns list of {body, position, person, responsibility, trigger_condition}
        """
        with self.neo4j.driver.session() as session:
            result = session.run(
                """
                MATCH (h:Hazard {name: $hazard_name})
                MATCH (c:County {county_code: $county_code})
                MATCH (body:Body)-[:GOVERNS]->(h)
                MATCH (body)-[:GOVERNS]->(c)
                MATCH (pos:Position)-[:BELONGS_TO]->(body)
                OPTIONAL MATCH (resp:Responsibility)-[:ASSIGNED_TO]->(pos)
                WHERE resp.trigger_hazard = $hazard_name
                OPTIONAL MATCH (p:Person)-[:HOLDS_POSITION]->(pos)
                RETURN body.name AS body_name, body.sector AS sector,
                       pos.title AS position_title,
                       resp.action AS required_action,
                       resp.trigger_condition AS trigger_condition,
                       p.name AS incumbent_name, p.contact AS incumbent_contact
                """,
                county_code=county_code,
                hazard_name=hazard_name,
            )
            return [dict(r) for r in result]

    # ── Run all inferences ──────────────────────────────────────────

    def run_all(self, county_code: str | None = None) -> dict[str, Any]:
        """Run all inference queries and return results."""
        logger.info("Running all inferences...")
        results = {}

        try:
            results["compound"] = self.detect_compound_hazards(county_code)
            self.create_compound_edges(results["compound"])
        except Exception as e:
            logger.error("Compound hazard detection failed: %s", e)
            results["compound"] = []

        try:
            results["chronic"] = self.detect_chronic_patterns()
            self.create_chronic_edges(results["chronic"])
        except Exception as e:
            logger.error("Chronic pattern detection failed: %s", e)
            results["chronic"] = []

        try:
            results["catchment_collapse"] = self.detect_catchment_collapse(county_code)
            self.create_catchment_edges(results["catchment_collapse"])
        except Exception as e:
            logger.error("Catchment collapse detection failed: %s", e)
            results["catchment_collapse"] = []

        try:
            results["preemptive"] = self.detect_preemptive_alerts(county_code)
            self.create_preemptive_edges(results["preemptive"])
        except Exception as e:
            logger.error("Pre-emptive alert detection failed: %s", e)
            results["preemptive"] = []

        try:
            results["protection_gaps"] = self.detect_protection_gaps(county_code)
        except Exception as e:
            logger.error("Protection gap detection failed: %s", e)
            results["protection_gaps"] = []

        try:
            results["policy_gaps"] = self.detect_policy_gaps(county_code)
        except Exception as e:
            logger.error("Policy gap detection failed: %s", e)
            results["policy_gaps"] = []

        return results
