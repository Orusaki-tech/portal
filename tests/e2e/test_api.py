from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.engine.adapters.repository import (
    FakeTaskGridRepository,
    FakeUserRepository,
)
from backend.engine.bootstrap import bootstrap
from backend.engine.domain.models import (
    MarketplaceListing,
    Polygon,
    TaskGrid,
    User,
)
from backend.engine.entrypoints.api import app, get_bus
from backend.engine.service_layer.messagebus import MessageBus


@pytest.fixture
def seeded_bus() -> MessageBus:
    polygon_id = uuid4()
    grid_id = uuid4()
    user_id = uuid4()

    grid = TaskGrid(
        id=grid_id, initiative_id=uuid4(),
        geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        polygons=[
            Polygon(
                id=polygon_id, task_grid_id=grid_id, polygon_set_id=uuid4(),
                original_geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            )
        ],
    )

    user = User(id=user_id, email="test@test.com", name="Test", role="annotator")

    bus = bootstrap(
        grid_repo=FakeTaskGridRepository(),
        user_repo=FakeUserRepository(),
    )
    bus.uow.grid_repo.add(grid)
    bus.uow.user_repo.add(user)

    bus._polygon_id = polygon_id
    bus._grid_id = grid_id
    bus._user_id = user_id

    return bus


@pytest.fixture
def client(seeded_bus: MessageBus) -> TestClient:
    app.dependency_overrides[get_bus] = lambda: seeded_bus
    return TestClient(app)


class TestHealth:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestUploadDataset:
    def test_upload_valid(self, client: TestClient, seeded_bus: MessageBus) -> None:
        response = client.post(
            "/api/datasets/upload",
            json={
                "user_id": str(seeded_bus._user_id),
                "name": "Test Set",
                "geometries": [
                    "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["polygon_count"] == 1

    def test_upload_missing_user_fails(self, client: TestClient) -> None:
        response = client.post(
            "/api/datasets/upload",
            json={
                "user_id": str(uuid4()),
                "name": "Test Set",
                "geometries": ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"],
            },
        )
        assert response.status_code == 400


class TestValidatePolygon:
    def test_validate_valid(self, client: TestClient, seeded_bus: MessageBus) -> None:
        response = client.post(
            "/api/datasets/validate",
            json={
                "grid_id": str(seeded_bus._grid_id),
                "polygon_id": str(seeded_bus._polygon_id),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "validated"
        assert data["polygon_id"] == str(seeded_bus._polygon_id)

    def test_validate_missing_grid_fails(self, client: TestClient) -> None:
        response = client.post(
            "/api/datasets/validate",
            json={
                "grid_id": str(uuid4()),
                "polygon_id": str(uuid4()),
            },
        )
        assert response.status_code == 400


class TestCorrectBoundary:
    def test_correct_valid(self, client: TestClient, seeded_bus: MessageBus) -> None:
        response = client.post(
            "/api/polygons/correct",
            json={
                "grid_id": str(seeded_bus._grid_id),
                "polygon_id": str(seeded_bus._polygon_id),
                "user_id": str(seeded_bus._user_id),
                "new_geometry": "POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "corrected"

    def test_correct_missing_grid_fails(self, client: TestClient) -> None:
        response = client.post(
            "/api/polygons/correct",
            json={
                "grid_id": str(uuid4()),
                "polygon_id": str(uuid4()),
                "user_id": str(uuid4()),
                "new_geometry": "POLYGON((0 0, 2 0, 2 1, 0 1, 0 0))",
            },
        )
        assert response.status_code == 400


class TestCreateInitiative:
    def test_create_initiative(self, client: TestClient) -> None:
        response = client.post(
            "/api/initiatives",
            json={
                "owner_id": str(uuid4()),
                "name": "Test Initiative",
                "region": "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "draft"
        assert data["name"] == "Test Initiative"


class TestLockGridBlock:
    def test_lock_grid(self, client: TestClient, seeded_bus: MessageBus) -> None:
        response = client.post(
            "/api/grids/lock",
            json={
                "grid_id": str(seeded_bus._grid_id),
                "user_id": str(seeded_bus._user_id),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"


class TestTopUpCredits:
    def test_top_up_valid(self, client: TestClient, seeded_bus: MessageBus) -> None:
        response = client.post(
            "/api/credits/top-up",
            json={
                "user_id": str(seeded_bus._user_id),
                "amount": 100,
            },
        )
        assert response.status_code == 200
        assert response.json()["credits_remaining"] == 100.0

    def test_top_up_missing_user(self, client: TestClient) -> None:
        response = client.post(
            "/api/credits/top-up",
            json={"user_id": str(uuid4()), "amount": 50},
        )
        assert response.status_code == 400


class TestRequestExport:
    def test_export_valid(self, client: TestClient, seeded_bus: MessageBus) -> None:
        response = client.post(
            "/api/exports",
            json={
                "user_id": str(seeded_bus._user_id),
                "export_format": "geojson",
                "source_type": "initiative",
                "source_id": str(uuid4()),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["export_format"] == "geojson"

    def test_export_bad_format(self, client: TestClient, seeded_bus: MessageBus) -> None:
        response = client.post(
            "/api/exports",
            json={
                "user_id": str(seeded_bus._user_id),
                "export_format": "pdf",
                "source_type": "initiative",
                "source_id": str(uuid4()),
            },
        )
        assert response.status_code == 400


class TestGenerateGrids:
    def test_generate_grids_valid(self, client: TestClient, seeded_bus: MessageBus) -> None:
        bus = seeded_bus
        from backend.engine.domain.models import Initiative
        initiative = Initiative(id=uuid4(), owner_id=bus._user_id, name="Grid Gen",
                                region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))")
        bus.uow.initiative_repo.add(initiative)

        response = client.post(
            "/api/initiatives/generate-grids",
            json={"initiative_id": str(initiative.id)},
        )
        assert response.status_code == 200
        assert response.json()["grids_generated"] > 0


class TestAssignParticipant:
    def test_assign_valid(self, client: TestClient, seeded_bus: MessageBus) -> None:
        bus = seeded_bus
        from backend.engine.domain.models import Initiative
        initiative = Initiative(id=uuid4(), owner_id=bus._user_id, name="Assign Test",
                                region="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))")
        bus.uow.initiative_repo.add(initiative)

        response = client.post(
            "/api/initiatives/assign",
            json={
                "initiative_id": str(initiative.id),
                "user_id": str(bus._user_id),
                "role": "reviewer",
            },
        )
        assert response.status_code == 200
        assert response.json()["role"] == "reviewer"


class TestMarketplace:
    def test_create_listing(self, client: TestClient, seeded_bus: MessageBus) -> None:
        response = client.post(
            "/api/marketplace/listings",
            json={
                "seller_id": str(seeded_bus._user_id),
                "dataset_id": str(uuid4()),
                "title": "Test Dataset",
                "price_tokens": 50.0,
            },
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Test Dataset"

    def test_purchase_listing(self, client: TestClient, seeded_bus: MessageBus) -> None:
        bus = seeded_bus
        seller = User(id=uuid4(), email="seller@test.com", name="Seller", role="annotator", credits_remaining=500)
        bus.uow.user_repo.add(seller)
        bus.uow.user_repo.get(bus._user_id).credits_remaining = 200

        listing = MarketplaceListing(
            listing_id=uuid4(), seller_id=seller.id, dataset_id=uuid4(),
            title="For Sale", price_tokens=30.0,
        )
        bus.uow.marketplace_repo.add_listing(listing)

        response = client.post(
            "/api/marketplace/purchase",
            json={
                "listing_id": str(listing.listing_id),
                "buyer_id": str(bus._user_id),
            },
        )
        assert response.status_code == 200
        assert response.json()["tokens_paid"] == 30.0
