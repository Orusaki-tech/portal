from uuid import uuid4

import pytest

from backend.engine.domain.events import (
    BoundaryCorrected,
    GridBlockCompleted,
    LowConfidenceDetected,
    PolygonValidated,
)
from backend.engine.domain.models import (
    ConfidenceScore,
    GridStatus,
    Initiative,
    Polygon,
    QaStatus,
    TaskGrid,
    User,
    VertexMetric,
)
from backend.engine.domain.models import InitiativeStatus


class TestPolygon:
    def test_high_confidence_validation(self) -> None:
        polygon = Polygon(
            id=uuid4(), task_grid_id=uuid4(), polygon_set_id=uuid4(),
            original_geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        score = ConfidenceScore(
            overall=0.92,
            per_vertex=[
                VertexMetric(0, 0.1, 0.8, 0.2, 0.92),
                VertexMetric(1, 0.1, 0.8, 0.2, 0.92),
                VertexMetric(2, 0.1, 0.8, 0.2, 0.92),
                VertexMetric(3, 0.1, 0.8, 0.2, 0.92),
            ],
        )
        polygon.validate(score, threshold=0.70)
        assert polygon.qa_status == QaStatus.VALIDATED
        assert polygon.confidence_avg == 0.92

    def test_low_confidence_validation(self) -> None:
        polygon = Polygon(
            id=uuid4(), task_grid_id=uuid4(), polygon_set_id=uuid4(),
            original_geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        score = ConfidenceScore(
            overall=0.45,
            per_vertex=[
                VertexMetric(0, 2.5, 0.3, 0.7, 0.45),
                VertexMetric(1, 2.5, 0.3, 0.7, 0.45),
                VertexMetric(2, 2.5, 0.3, 0.7, 0.45),
                VertexMetric(3, 2.5, 0.3, 0.7, 0.45),
            ],
        )
        polygon.validate(score, threshold=0.70)
        assert polygon.qa_status == QaStatus.LOW_CONFIDENCE
        assert polygon.confidence_avg == 0.45

    def test_correction_updates_status(self) -> None:
        polygon = Polygon(
            id=uuid4(), task_grid_id=uuid4(), polygon_set_id=uuid4(),
            original_geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        new_geom = "POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))"
        polygon.correct(new_geom)
        assert polygon.qa_status == QaStatus.CORRECTED
        assert polygon.corrected_geometry == new_geom

    def test_escalation(self) -> None:
        polygon = Polygon(
            id=uuid4(), task_grid_id=uuid4(), polygon_set_id=uuid4(),
            original_geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        polygon.escalate()
        assert polygon.qa_status == QaStatus.ESCALATED


class TestConfidenceScore:
    def test_valid_confidence(self) -> None:
        score = ConfidenceScore(
            overall=0.85,
            per_vertex=[
                VertexMetric(0, 0.1, 0.8, 0.2, 0.85),
            ],
        )
        assert score.overall == 0.85

    def test_rejects_out_of_range_overall(self) -> None:
        with pytest.raises(ValueError):
            ConfidenceScore(
                overall=1.5,
                per_vertex=[
                    VertexMetric(0, 0.1, 0.8, 0.2, 0.85),
                ],
            )

    def test_rejects_out_of_range_per_vertex(self) -> None:
        with pytest.raises(ValueError):
            ConfidenceScore(
                overall=0.85,
                per_vertex=[
                    VertexMetric(0, 0.1, 0.8, 0.2, -0.1),
                ],
            )


class TestTaskGrid:
    def test_lock_sets_status_and_user(self) -> None:
        grid = TaskGrid(
            id=uuid4(), initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        user_id = uuid4()
        grid.lock(user_id)
        assert grid.status == GridStatus.IN_PROGRESS
        assert grid.assigned_user_id == user_id
        assert grid.locked_at is not None

    def test_cannot_lock_completed_grid(self) -> None:
        grid = TaskGrid(
            id=uuid4(), initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        grid.complete()
        with pytest.raises(ValueError):
            grid.lock(uuid4())

    def test_release_returns_to_pending(self) -> None:
        grid = TaskGrid(
            id=uuid4(), initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        grid.lock(uuid4())
        grid.release()
        assert grid.status == GridStatus.PENDING
        assert grid.assigned_user_id is None
        assert grid.locked_at is None

    def test_submit_review(self) -> None:
        grid = TaskGrid(
            id=uuid4(), initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        grid.lock(uuid4())
        grid.submit_review()
        assert grid.status == GridStatus.AWAITING_REVIEW

    def test_complete_emits_event(self) -> None:
        grid = TaskGrid(
            id=uuid4(), initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        grid.lock(uuid4())
        grid.submit_review()
        grid.complete()
        assert grid.status == GridStatus.COMPLETE
        assert grid.completed_at is not None
        events = grid.events
        assert len(events) == 1
        assert isinstance(events[0], GridBlockCompleted)
        assert events[0].grid_id == grid.id
        assert events[0].initiative_id == grid.initiative_id

    def test_dispute_sets_notes(self) -> None:
        grid = TaskGrid(
            id=uuid4(), initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        grid.dispute("Boundary does not match imagery")
        assert grid.status == GridStatus.DISPUTED
        assert grid.review_notes == "Boundary does not match imagery"


class TestUser:
    def test_deduct_credits(self) -> None:
        from decimal import Decimal
        user = User(
            id=uuid4(), email="test@test.com", name="Test",
            role="annotator", credits_remaining=Decimal("100"),
        )
        user.deduct_credits(Decimal("25"))
        assert user.credits_remaining == Decimal("75")

    def test_deduct_insufficient_credits_raises(self) -> None:
        from decimal import Decimal
        user = User(
            id=uuid4(), email="test@test.com", name="Test",
            role="annotator", credits_remaining=Decimal("10"),
        )
        with pytest.raises(ValueError, match="Insufficient credits"):
            user.deduct_credits(Decimal("25"))

    def test_negative_credits_on_create_raises(self) -> None:
        from decimal import Decimal
        with pytest.raises(ValueError):
            User(
                id=uuid4(), email="test@test.com", name="Test",
                role="annotator", credits_remaining=Decimal("-5"),
            )


class TestInitiative:
    def test_activate(self) -> None:
        initiative = Initiative(
            id=uuid4(), owner_id=uuid4(), name="Test Initiative",
            region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        initiative.activate()
        assert initiative.status == InitiativeStatus.ACTIVE

    def test_cannot_activate_active_initiative(self) -> None:
        initiative = Initiative(
            id=uuid4(), owner_id=uuid4(), name="Test Initiative",
            region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        initiative.activate()
        with pytest.raises(ValueError):
            initiative.activate()

    def test_complete_sets_timestamp(self) -> None:
        initiative = Initiative(
            id=uuid4(), owner_id=uuid4(), name="Test Initiative",
            region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        initiative.complete()
        assert initiative.status == InitiativeStatus.COMPLETE
        assert initiative.completed_at is not None


class TestEvents:
    def test_polygon_validated_event(self) -> None:
        pid = uuid4()
        event = PolygonValidated(pid, confidence=0.92, is_ambiguous=False)
        assert event.polygon_id == pid
        assert event.confidence == 0.92
        assert not event.is_ambiguous

    def test_low_confidence_detected_event(self) -> None:
        pid = uuid4()
        event = LowConfidenceDetected(pid, confidence=0.45)
        assert event.polygon_id == pid
        assert event.confidence == 0.45

    def test_boundary_corrected_event(self) -> None:
        pid = uuid4()
        uid = uuid4()
        event = BoundaryCorrected(pid, uid, "POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))")
        assert event.polygon_id == pid
        assert event.user_id == uid
        assert event.new_geometry == "POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))"
