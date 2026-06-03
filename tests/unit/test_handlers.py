from uuid import UUID, uuid4

import pytest

from backend.engine.bootstrap import bootstrap
from backend.engine.domain.commands import (
    AssignParticipant,
    CorrectBoundary,
    CreateInitiative,
    GenerateGridBlocks,
    JoinHackathon,
    ListDatasetForSale,
    LockGridBlock,
    PurchaseDataset,
    RequestExport,
    SubmitHackathonResult,
    TopUpCredits,
    UploadPolygonSet,
    ValidatePolygon,
)
from backend.engine.domain.models import (
    GridStatus,
    Initiative,
    InitiativeStatus,
    MarketplaceListing,
    Polygon,
    QaStatus,
    TaskGrid,
    User,
)


class TestValidatePolygon:
    def test_validates_square_polygon(self) -> None:
        bus = bootstrap()
        polygon_id = uuid4()
        grid_id = uuid4()
        user_id = uuid4()
        user = User(
            id=user_id, email="test@test.com", name="Test", role="annotator", credits_remaining=100
        )
        grid = TaskGrid(
            id=grid_id,
            initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            polygons=[
                Polygon(
                    id=polygon_id,
                    task_grid_id=grid_id,
                    polygon_set_id=uuid4(),
                    original_geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                )
            ],
        )
        bus.uow.grid_repo.add(grid)
        bus.uow.user_repo.add(user)

        results = bus.handle(
            ValidatePolygon(grid_id=grid_id, polygon_id=polygon_id, user_id=user_id)
        )

        assert results[0]["polygon_id"] == str(polygon_id)
        assert results[0]["status"] in ("validated", "low_confidence")
        assert 0.0 <= results[0]["confidence"] <= 1.0

    def test_validates_sliver_as_low_confidence(self) -> None:
        bus = bootstrap()
        polygon_id = uuid4()
        grid_id = uuid4()
        grid = TaskGrid(
            id=grid_id,
            initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 0.001, 0 0.001, 0 0))",
            polygons=[
                Polygon(
                    id=polygon_id,
                    task_grid_id=grid_id,
                    polygon_set_id=uuid4(),
                    original_geometry="POLYGON((0 0, 1 0, 1 0.001, 0 0.001, 0 0))",
                )
            ],
        )
        bus.uow.grid_repo.add(grid)

        results = bus.handle(ValidatePolygon(grid_id=grid_id, polygon_id=polygon_id))

        assert results[0]["status"] == "low_confidence"
        assert results[0]["confidence"] < 0.70

    def test_grid_not_found_raises(self) -> None:
        bus = bootstrap()
        with pytest.raises(ValueError):
            bus.handle(ValidatePolygon(grid_id=uuid4(), polygon_id=uuid4()))

    def test_polygon_not_in_grid(self) -> None:
        bus = bootstrap()
        grid_id = uuid4()
        grid = TaskGrid(
            id=grid_id,
            initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        bus.uow.grid_repo.add(grid)

        with pytest.raises(ValueError):
            bus.handle(ValidatePolygon(grid_id=grid_id, polygon_id=uuid4()))


class TestUploadPolygonSet:
    def test_uploads_polygons(self) -> None:
        bus = bootstrap()
        user = User(id=uuid4(), email="test@test.com", name="Test", role="annotator")
        bus.uow.user_repo.add(user)

        results = bus.handle(
            UploadPolygonSet(
                user_id=user.id,
                name="Test Set",
                geometries=[
                    "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                    "POLYGON((2 2, 3 2, 3 3, 2 3, 2 2))",
                ],
            )
        )

        assert results[0]["polygon_count"] == 2

    def test_user_not_found_raises(self) -> None:
        bus = bootstrap()
        with pytest.raises(ValueError):
            bus.handle(
                UploadPolygonSet(
                    user_id=uuid4(),
                    name="Test Set",
                    geometries=["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"],
                )
            )


class TestCorrectBoundary:
    def test_corrects_polygon(self) -> None:
        bus = bootstrap()
        polygon_id = uuid4()
        grid_id = uuid4()
        grid = TaskGrid(
            id=grid_id,
            initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            polygons=[
                Polygon(
                    id=polygon_id,
                    task_grid_id=grid_id,
                    polygon_set_id=uuid4(),
                    original_geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                )
            ],
        )
        bus.uow.grid_repo.add(grid)

        results = bus.handle(
            CorrectBoundary(
                grid_id=grid_id,
                polygon_id=polygon_id,
                user_id=uuid4(),
                new_geometry="POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))",
            )
        )

        assert results[0]["polygon_id"] == str(polygon_id)
        assert results[0]["status"] == "corrected"
        assert grid.polygons[0].qa_status == QaStatus.CORRECTED
        assert grid.polygons[0].corrected_geometry == "POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))"


class TestConsensusTrigger:
    def test_two_corrections_trigger_consensus(self) -> None:
        bus = bootstrap()
        polygon_id = uuid4()
        grid_id = uuid4()
        user_a = uuid4()
        user_b = uuid4()
        grid = TaskGrid(
            id=grid_id,
            initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            polygons=[
                Polygon(
                    id=polygon_id,
                    task_grid_id=grid_id,
                    polygon_set_id=uuid4(),
                    original_geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                )
            ],
        )
        bus.uow.grid_repo.add(grid)

        bus.handle(
            CorrectBoundary(
                grid_id=grid_id,
                polygon_id=polygon_id,
                user_id=user_a,
                new_geometry="POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))",
            )
        )
        bus.handle(
            CorrectBoundary(
                grid_id=grid_id,
                polygon_id=polygon_id,
                user_id=user_b,
                new_geometry="POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))",
            )
        )

        polygon = next(p for p in grid.polygons if p.id == polygon_id)
        assert polygon.qa_status == QaStatus.VALIDATED
        assert polygon.confidence_avg == 0.95

    def test_single_correction_does_not_trigger_consensus(self) -> None:
        bus = bootstrap()
        polygon_id = uuid4()
        grid_id = uuid4()
        grid = TaskGrid(
            id=grid_id,
            initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            polygons=[
                Polygon(
                    id=polygon_id,
                    task_grid_id=grid_id,
                    polygon_set_id=uuid4(),
                    original_geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                )
            ],
        )
        bus.uow.grid_repo.add(grid)

        bus.handle(
            CorrectBoundary(
                grid_id=grid_id,
                polygon_id=polygon_id,
                user_id=uuid4(),
                new_geometry="POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))",
            )
        )

        polygon = next(p for p in grid.polygons if p.id == polygon_id)
        assert polygon.qa_status == QaStatus.CORRECTED
        assert polygon.confidence_avg is None


class TestCreateInitiative:
    def test_creates_and_persists_initiative(self) -> None:
        bus = bootstrap()
        owner_id = uuid4()
        results = bus.handle(
            CreateInitiative(
                owner_id=owner_id,
                name="Test Initiative",
                region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            )
        )
        assert results[0]["status"] == "draft"
        assert results[0]["name"] == "Test Initiative"

        initiative_id = UUID(results[0]["initiative_id"])
        saved = bus.uow.initiative_repo.get(initiative_id)
        assert saved is not None
        assert saved.owner_id == owner_id
        assert saved.name == "Test Initiative"


class TestLockGridBlock:
    def test_locks_grid(self) -> None:
        bus = bootstrap()
        grid_id = uuid4()
        user_id = uuid4()
        grid = TaskGrid(
            id=grid_id,
            initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        bus.uow.grid_repo.add(grid)

        results = bus.handle(LockGridBlock(grid_id=grid_id, user_id=user_id))

        assert results[0]["status"] == "in_progress"
        assert results[0]["assigned_user_id"] == str(user_id)
        assert grid.status == GridStatus.IN_PROGRESS
        assert grid.assigned_user_id == user_id


class TestEventDispatching:
    def test_correction_triggers_events(self) -> None:
        bus = bootstrap()
        polygon_id = uuid4()
        grid_id = uuid4()
        grid = TaskGrid(
            id=grid_id,
            initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            polygons=[
                Polygon(
                    id=polygon_id,
                    task_grid_id=grid_id,
                    polygon_set_id=uuid4(),
                    original_geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                )
            ],
        )
        bus.uow.grid_repo.add(grid)

        results = bus.handle(
            CorrectBoundary(
                grid_id=grid_id,
                polygon_id=polygon_id,
                user_id=uuid4(),
                new_geometry="POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))",
            )
        )

        assert results[0]["status"] == "corrected"

    def test_correction_persists_correction_record(self) -> None:
        bus = bootstrap()
        polygon_id = uuid4()
        grid_id = uuid4()
        user_id = uuid4()
        grid = TaskGrid(
            id=grid_id,
            initiative_id=uuid4(),
            geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            polygons=[
                Polygon(
                    id=polygon_id,
                    task_grid_id=grid_id,
                    polygon_set_id=uuid4(),
                    original_geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                )
            ],
        )
        bus.uow.grid_repo.add(grid)

        bus.handle(
            CorrectBoundary(
                grid_id=grid_id,
                polygon_id=polygon_id,
                user_id=user_id,
                new_geometry="POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))",
            )
        )

        corrections = bus.uow.correction_repo.get_by_polygon(polygon_id)
        assert len(corrections) == 1
        assert corrections[0].user_id == user_id
        assert corrections[0].corrected_geometry == "POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))"


class TestTopUpCredits:
    def test_top_up_increases_credits(self) -> None:
        bus = bootstrap()
        user = User(
            id=uuid4(), email="test@test.com", name="Test", role="annotator", credits_remaining=50
        )
        bus.uow.user_repo.add(user)

        results = bus.handle(TopUpCredits(user_id=user.id, amount=100))

        assert results[0]["credits_remaining"] == 150.0

    def test_top_up_user_not_found(self) -> None:
        bus = bootstrap()
        with pytest.raises(ValueError, match="not found"):
            bus.handle(TopUpCredits(user_id=uuid4(), amount=100))


class TestRequestExport:
    def test_creates_export_job(self) -> None:
        bus = bootstrap()
        user = User(id=uuid4(), email="test@test.com", name="Test", role="annotator")
        bus.uow.user_repo.add(user)

        results = bus.handle(
            RequestExport(
                user_id=user.id,
                export_format="geojson",
                source_type="initiative",
                source_id=uuid4(),
            )
        )

        assert results[0]["status"] == "pending"
        assert results[0]["export_format"] == "geojson"

    def test_unsupported_format(self) -> None:
        bus = bootstrap()
        user = User(id=uuid4(), email="test@test.com", name="Test", role="annotator")
        bus.uow.user_repo.add(user)

        with pytest.raises(ValueError, match="Unsupported format"):
            bus.handle(
                RequestExport(
                    user_id=user.id,
                    export_format="pdf",
                    source_type="initiative",
                    source_id=uuid4(),
                )
            )

    def test_export_user_not_found(self) -> None:
        bus = bootstrap()
        with pytest.raises(ValueError, match="not found"):
            bus.handle(
                RequestExport(
                    user_id=uuid4(),
                    export_format="geojson",
                    source_type="initiative",
                    source_id=uuid4(),
                )
            )


class TestGenerateGridBlocks:
    def test_generates_grids_for_initiative(self) -> None:
        bus = bootstrap()
        initiative = Initiative(
            id=uuid4(),
            owner_id=uuid4(),
            name="Test",
            region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        bus.uow.initiative_repo.add(initiative)

        results = bus.handle(GenerateGridBlocks(initiative_id=initiative.id))

        assert results[0]["grids_generated"] > 0
        grids = bus.uow.grid_repo.get_by_initiative(initiative.id)
        assert len(grids) == results[0]["grids_generated"]

    def test_initiative_not_found(self) -> None:
        bus = bootstrap()
        with pytest.raises(ValueError, match="not found"):
            bus.handle(GenerateGridBlocks(initiative_id=uuid4()))

    def test_duplicate_grid_generation_raises(self) -> None:
        bus = bootstrap()
        initiative = Initiative(
            id=uuid4(),
            owner_id=uuid4(),
            name="Test",
            region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        )
        bus.uow.initiative_repo.add(initiative)
        bus.uow.grid_repo.add(
            TaskGrid(
                id=uuid4(),
                initiative_id=initiative.id,
                geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            )
        )

        with pytest.raises(ValueError, match="already exist"):
            bus.handle(GenerateGridBlocks(initiative_id=initiative.id))


class TestAssignParticipant:
    def test_assigns_user_to_initiative(self) -> None:
        bus = bootstrap()
        initiative = Initiative(
            id=uuid4(), owner_id=uuid4(), name="Test", region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        )
        user = User(id=uuid4(), email="test@test.com", name="Test", role="annotator")
        bus.uow.initiative_repo.add(initiative)
        bus.uow.user_repo.add(user)

        results = bus.handle(
            AssignParticipant(initiative_id=initiative.id, user_id=user.id, role="annotator")
        )

        assert results[0]["role"] == "annotator"
        participants = bus.uow.participant_repo.list_by_initiative(initiative.id)
        assert len(participants) == 1

    def test_assign_initiative_not_found(self) -> None:
        bus = bootstrap()
        with pytest.raises(ValueError):
            bus.handle(AssignParticipant(initiative_id=uuid4(), user_id=uuid4()))

    def test_assign_user_not_found(self) -> None:
        bus = bootstrap()
        initiative = Initiative(
            id=uuid4(), owner_id=uuid4(), name="Test", region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        )
        bus.uow.initiative_repo.add(initiative)
        with pytest.raises(ValueError):
            bus.handle(AssignParticipant(initiative_id=initiative.id, user_id=uuid4()))


class TestListDatasetForSale:
    def test_creates_listing(self) -> None:
        bus = bootstrap()
        user = User(id=uuid4(), email="test@test.com", name="Test", role="annotator")
        bus.uow.user_repo.add(user)

        results = bus.handle(
            ListDatasetForSale(
                seller_id=user.id, dataset_id=uuid4(), title="Test Dataset", price_tokens=50.0
            )
        )

        assert results[0]["title"] == "Test Dataset"
        assert results[0]["price_tokens"] == 50.0

    def test_listing_seller_not_found(self) -> None:
        bus = bootstrap()
        with pytest.raises(ValueError):
            bus.handle(
                ListDatasetForSale(
                    seller_id=uuid4(), dataset_id=uuid4(), title="Test", price_tokens=10.0
                )
            )


class TestPurchaseDataset:
    def test_purchase_deducts_credits(self) -> None:
        bus = bootstrap()
        seller = User(id=uuid4(), email="seller@test.com", name="Seller", role="annotator")
        buyer = User(
            id=uuid4(),
            email="buyer@test.com",
            name="Buyer",
            role="annotator",
            credits_remaining=200,
        )
        bus.uow.user_repo.add(seller)
        bus.uow.user_repo.add(buyer)

        listing = MarketplaceListing(
            listing_id=uuid4(),
            seller_id=seller.id,
            dataset_id=uuid4(),
            title="Test Dataset",
            price_tokens=50.0,
        )
        bus.uow.marketplace_repo.add_listing(listing)

        results = bus.handle(PurchaseDataset(listing_id=listing.listing_id, buyer_id=buyer.id))

        assert results[0]["tokens_paid"] == 50.0
        assert buyer.credits_remaining == 150

    def test_purchase_listing_not_found(self) -> None:
        bus = bootstrap()
        with pytest.raises(ValueError):
            bus.handle(PurchaseDataset(listing_id=uuid4(), buyer_id=uuid4()))

    def test_purchase_sold_listing_raises(self) -> None:
        bus = bootstrap()
        seller = User(id=uuid4(), email="seller@test.com", name="Seller", role="annotator")
        buyer = User(
            id=uuid4(),
            email="buyer@test.com",
            name="Buyer",
            role="annotator",
            credits_remaining=200,
        )
        bus.uow.user_repo.add(seller)
        bus.uow.user_repo.add(buyer)

        listing = MarketplaceListing(
            listing_id=uuid4(),
            seller_id=seller.id,
            dataset_id=uuid4(),
            title="Sold Dataset",
            price_tokens=50.0,
            status="sold",
        )
        bus.uow.marketplace_repo.add_listing(listing)

        with pytest.raises(ValueError, match="not active"):
            bus.handle(PurchaseDataset(listing_id=listing.listing_id, buyer_id=buyer.id))

    def test_purchase_insufficient_credits(self) -> None:
        bus = bootstrap()
        seller = User(id=uuid4(), email="seller@test.com", name="Seller", role="annotator")
        buyer = User(
            id=uuid4(), email="buyer@test.com", name="Buyer", role="annotator", credits_remaining=10
        )
        bus.uow.user_repo.add(seller)
        bus.uow.user_repo.add(buyer)

        listing = MarketplaceListing(
            listing_id=uuid4(),
            seller_id=seller.id,
            dataset_id=uuid4(),
            title="Expensive Dataset",
            price_tokens=50.0,
        )
        bus.uow.marketplace_repo.add_listing(listing)

        with pytest.raises(ValueError, match="Insufficient credits"):
            bus.handle(PurchaseDataset(listing_id=listing.listing_id, buyer_id=buyer.id))


class TestJoinHackathon:
    def test_join_hackathon_creates_entry(self) -> None:
        bus = bootstrap()
        initiative_id = uuid4()
        user_id = uuid4()
        initiative = Initiative(
            id=initiative_id,
            owner_id=user_id,
            name="Hackathon",
            region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            status=InitiativeStatus.ACTIVE,
            hackathon_mode=True,
        )
        bus.uow.initiative_repo.add(initiative)

        bus.handle(JoinHackathon(initiative_id=initiative_id, user_id=user_id))
        entry = bus.uow.leaderboard_repo.get_by_user_and_initiative(initiative_id, user_id)
        assert entry is not None
        assert entry.score == 0.0

    def test_join_non_hackathon_raises(self) -> None:
        bus = bootstrap()
        initiative = Initiative(
            id=uuid4(),
            owner_id=uuid4(),
            name="Normal",
            region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            status=InitiativeStatus.ACTIVE,
            hackathon_mode=False,
        )
        bus.uow.initiative_repo.add(initiative)
        with pytest.raises(ValueError, match="not a hackathon"):
            bus.handle(JoinHackathon(initiative_id=initiative.id, user_id=uuid4()))

    def test_join_twice_raises(self) -> None:
        bus = bootstrap()
        initiative_id = uuid4()
        user_id = uuid4()
        initiative = Initiative(
            id=initiative_id,
            owner_id=uuid4(),
            name="Hackathon",
            region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            status=InitiativeStatus.ACTIVE,
            hackathon_mode=True,
        )
        bus.uow.initiative_repo.add(initiative)
        bus.handle(JoinHackathon(initiative_id=initiative_id, user_id=user_id))
        with pytest.raises(ValueError, match="already joined"):
            bus.handle(JoinHackathon(initiative_id=initiative_id, user_id=user_id))


class TestSubmitHackathonResult:
    def test_submit_updates_score(self) -> None:
        bus = bootstrap()
        initiative_id = uuid4()
        user_id = uuid4()
        initiative = Initiative(
            id=initiative_id,
            owner_id=user_id,
            name="Hackathon",
            region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            status=InitiativeStatus.ACTIVE,
            hackathon_mode=True,
        )
        bus.uow.initiative_repo.add(initiative)
        bus.handle(JoinHackathon(initiative_id=initiative_id, user_id=user_id))
        bus.handle(
            SubmitHackathonResult(
                initiative_id=initiative_id, user_id=user_id, score=95.0, accuracy_pct=0.95
            )
        )
        entry = bus.uow.leaderboard_repo.get_by_user_and_initiative(initiative_id, user_id)
        assert entry is not None
        assert entry.score == 95.0
        assert entry.polygons_submitted == 1

    def test_submit_without_join_raises(self) -> None:
        bus = bootstrap()
        with pytest.raises(ValueError, match="not joined"):
            bus.handle(
                SubmitHackathonResult(
                    initiative_id=uuid4(), user_id=uuid4(), score=50.0, accuracy_pct=0.5
                )
            )
