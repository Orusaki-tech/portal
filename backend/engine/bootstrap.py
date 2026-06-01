from __future__ import annotations

from backend.engine.adapters.repository import (
    AbstractCorrectionRepository,
    AbstractExportRepository,
    AbstractInitiativeRepository,
    AbstractMarketplaceRepository,
    AbstractParticipantRepository,
    AbstractTaskGridRepository,
    AbstractUserRepository,
    FakeCorrectionRepository,
    FakeExportRepository,
    FakeInitiativeRepository,
    FakeMarketplaceRepository,
    FakeParticipantRepository,
    FakeTaskGridRepository,
    FakeUserRepository,
)
from backend.engine.domain.commands import (
    AssignParticipant,
    Command,
    CorrectBoundary,
    CreateInitiative,
    GenerateGridBlocks,
    ListDatasetForSale,
    LockGridBlock,
    PurchaseDataset,
    RequestExport,
    TopUpCredits,
    UploadPolygonSet,
    ValidatePolygon,
)
from backend.engine.domain.events import (
    BoundaryCorrected,
    CreditsExhausted,
    DatasetPurchased,
    Event,
    ExportCompleted,
    GridBlockCompleted,
    InitiativeCompleted,
    LowConfidenceDetected,
    PolygonValidated,
)
from backend.engine.service_layer.handlers import (
    handle_assign_participant,
    handle_check_grid_complete,
    handle_check_initiative_complete,
    handle_classify_confidence,
    handle_correct_boundary,
    handle_create_initiative,
    handle_credits_exhausted,
    handle_deduct_credits,
    handle_flag_for_review,
    handle_generate_grid_blocks,
    handle_list_dataset_for_sale,
    handle_lock_grid_block,
    handle_notify_export_complete,
    handle_purchase_dataset,
    handle_request_export,
    handle_top_up_credits,
    handle_update_geometry,
    handle_upload_polygon_set,
    handle_validate_polygon,
)
from backend.engine.service_layer.messagebus import MessageBus
from backend.engine.service_layer.unit_of_work import FakeUnitOfWork, UnitOfWork


def bootstrap(
    grid_repo: AbstractTaskGridRepository | None = None,
    user_repo: AbstractUserRepository | None = None,
    initiative_repo: AbstractInitiativeRepository | None = None,
    correction_repo: AbstractCorrectionRepository | None = None,
    export_repo: AbstractExportRepository | None = None,
    participant_repo: AbstractParticipantRepository | None = None,
    marketplace_repo: AbstractMarketplaceRepository | None = None,
    uow: UnitOfWork | None = None,
) -> MessageBus:
    uow = uow or FakeUnitOfWork(
        grid_repo=grid_repo or FakeTaskGridRepository(),
        user_repo=user_repo or FakeUserRepository(),
        initiative_repo=initiative_repo or FakeInitiativeRepository(),
        correction_repo=correction_repo or FakeCorrectionRepository(),
        export_repo=export_repo or FakeExportRepository(),
        participant_repo=participant_repo or FakeParticipantRepository(),
        marketplace_repo=marketplace_repo or FakeMarketplaceRepository(),
    )

    command_handlers: dict[type[Command], object] = {
        ValidatePolygon: handle_validate_polygon,
        UploadPolygonSet: handle_upload_polygon_set,
        CorrectBoundary: handle_correct_boundary,
        CreateInitiative: handle_create_initiative,
        LockGridBlock: handle_lock_grid_block,
        TopUpCredits: handle_top_up_credits,
        RequestExport: handle_request_export,
        GenerateGridBlocks: handle_generate_grid_blocks,
        AssignParticipant: handle_assign_participant,
        ListDatasetForSale: handle_list_dataset_for_sale,
        PurchaseDataset: handle_purchase_dataset,
    }

    event_handlers: dict[type[Event], list[object]] = {
        PolygonValidated: [handle_classify_confidence],
        LowConfidenceDetected: [handle_flag_for_review],
        BoundaryCorrected: [
            handle_update_geometry,
            handle_deduct_credits,
            handle_check_grid_complete,
        ],
        GridBlockCompleted: [handle_check_initiative_complete],
        InitiativeCompleted: [],
        CreditsExhausted: [handle_credits_exhausted],
        ExportCompleted: [handle_notify_export_complete],
        DatasetPurchased: [],
    }

    return MessageBus(
        uow=uow,
        command_handlers=command_handlers,
        event_handlers=event_handlers,
    )
