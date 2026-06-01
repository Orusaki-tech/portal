# Pattern Map

Architecture Patterns with Python (Percival & Gregory) — RealitySync mapping.

---

## Chapter-by-Chapter Map

| # | Pattern | Book Chapter | RealitySync Location | Key Abstraction |
|---|---|---|---|---|
| 1 | **Domain Model** | 1 | `backend/engine/domain/models.py` | `TaskGrid`, `Polygon`, `ConfidenceScore`, `VertexMetric` |
| 2 | **Domain Events** | 1 | `backend/engine/domain/events.py` | `PolygonValidated`, `LowConfidenceDetected`, `BoundaryCorrected` |
| 3 | **Repository** | 2 | `backend/engine/adapters/repository.py` | `AbstractTaskGridRepository(Protocol)`, `PostgresTaskGridRepository`, `FakeTaskGridRepository` |
| 4 | **Service Layer / Handlers** | 4 | `backend/engine/service_layer/handlers.py` | `handle_validate_polygon(cmd, uow)`, `handle_correct_boundary(cmd, uow)` |
| 5 | **Unit of Work** | 6 | `backend/engine/service_layer/unit_of_work.py` | `PostgresUnitOfWork` (contextmanager + `seen` + event dispatch) |
| 6 | **Aggregate** | 7 | `backend/engine/domain/models.py` | `TaskGrid` (consistency boundary for multi-user editing) |
| 7 | **Message Bus** | 8 | `backend/engine/service_layer/messagebus.py` | `MessageBus.handle(message)` — routes commands/events to handlers |
| 8 | **Dependency Injection** | 8 | `backend/engine/service_layer/messagebus.py` | Handlers receive UoW via injectable dependency |
| 9 | **Commands** | 8 | `backend/engine/domain/commands.py` | `ValidatePolygon`, `CorrectBoundary`, `UploadPolygonSet` |
| 10 | **Event-Driven Architecture** | 9 | `backend/engine/service_layer/messagebus.py` | UoW collects events → dispatches after commit |
| 11 | **CQRS** | 12 | `backend/engine/service_layer/handlers.py` + `dbt/models/` | Write: command handlers. Read: dbt marts + SQL views |
| 12 | **Bootstrap** | 13 | `backend/engine/bootstrap.py` | Singleton composition root wiring UoW, repos, bus, handlers |

---

## Package Structure

```
backend/engine/
├── __init__.py                # Package marker
├── config.py                  # Settings from env + edge_config.yaml
├── bootstrap.py               # DI composition root
├── domain/
│   ├── __init__.py
│   ├── models.py              # TaskGrid (aggregate), Polygon (entity), value objects
│   ├── events.py              # All domain events as dataclasses
│   └── commands.py            # All commands as dataclasses
├── service_layer/
│   ├── __init__.py
│   ├── handlers.py            # Command + event handler functions
│   ├── messagebus.py          # MessageBus: dispatcher + routing table
│   └── unit_of_work.py        # PostgresUnitOfWork: atomic context + event collection
├── adapters/
│   ├── __init__.py
│   ├── repository.py          # AbstractTaskGridRepository protocol + implementations
│   ├── stac_client.py         # External: Microsoft Planetary Computer API
│   └── email_sender.py        # External: notification service (stub for MVP)
├── entrypoints/
│   ├── __init__.py
│   ├── main.py                # Cloud Run Job entry: reads input, calls bus
│   ├── api.py                 # FastAPI: REST endpoints → bus
│   └── consumer.py            # Pub/Sub subscriber → bus
└── edge/
    ├── __init__.py
    ├── edge_detector.py       # Spectral-guided edge detection (K-means + snake)
    └── confidence_scorer.py   # Confidence formula (40/30/30 weighting)
```

---

## Dependency Injection Wiring (Text Diagram)

```
bootstrap.py
│
├── config = load_config()                    # Edge parameters, DB URL, STAC URL
├── stac_client = StacClient(config)          # Adapter
├── email_sender = EmailSender(config)        # Adapter (stub)
│
├── repo: AbstractTaskGridRepository = PostgresTaskGridRepository(connection)
├── uow: UnitOfWork = PostgresUnitOfWork(repo, connection_factory)
│
├── event_handlers = {
│     PolygonValidated:       [handle_classify_confidence],
│     LowConfidenceDetected:  [handle_flag_for_review, handle_notify_annotator],
│     BoundaryCorrected:      [handle_update_geometry, handle_deduct_credits],
│     GridBlockCompleted:     [handle_check_initiative_complete],
│     ...
│   }
├── command_handlers = {
│     ValidatePolygon:        handle_validate_polygon,
│     CorrectBoundary:        handle_correct_boundary,
│     UploadPolygonSet:       handle_upload_polygon_set,
│     ...
│   }
│
└── bus = MessageBus(uow, command_handlers, event_handlers)
         ↑                    ↑
    entrypoints/main.py    entrypoints/api.py
    entrypoints/consumer.py
```

---

## Command/Event Catalog

### Commands (imperative — "do this")

| Command | Payload | Handler | Side Effects |
|---|---|---|---|
| `ValidatePolygon` | `polygon_id, imagery_id, user_id` | `handle_validate_polygon` | Runs edge detection → publishes `PolygonValidated` or `LowConfidenceDetected` |
| `CorrectBoundary` | `polygon_id, user_id, new_geometry` | `handle_correct_boundary` | Updates polygon → deducts credits → checks grid completion → publishes `BoundaryCorrected` |
| `UploadPolygonSet` | `user_id, name, geometries[]` | `handle_upload_polygon_set` | Inserts polygons → creates TaskGrids if needed |
| `CreateInitiative` | `owner_id, name, region, grid_size, budget` | `handle_create_initiative` | Creates initiative → divides region into TaskGrids |
| `LockGridBlock` | `grid_id, user_id` | `handle_lock_grid_block` | Row-locks grid → sets `in_progress` → prevents double-assignment |

### Events (factual — "this happened")

| Event | Raised By | Handler(s) | Side Effects |
|---|---|---|---|
| `PolygonValidated` | `handle_validate_polygon` | `handle_classify_confidence` | Sets `confidence_avg`, updates `qa_status` |
| `LowConfidenceDetected` | `handle_classify_confidence` | `handle_flag_for_review`, `handle_notify_annotator` | Flags polygon in triage queue, sends notification |
| `BoundaryCorrected` | `handle_correct_boundary` | `handle_update_geometry`, `handle_deduct_credits`, `handle_check_grid_complete` | Writes correction, deducts credits, checks if grid is done |
| `GridBlockCompleted` | `handle_check_grid_complete` | `handle_check_initiative_complete` | Marks grid `complete`, checks initiative |
| `InitiativeCompleted` | `handle_check_initiative_complete` | `handle_generate_report`, `handle_export_data` | Generates PDF/GeoJSON, triggers export |

---

## Message Bus Flow

```
CLIENT                         BUS                          UOW                    DB
  │                             │                            │                     │
  │  bus.handle(cmd)            │                            │                     │
  │ ──────────────────────────> │                            │                     │
  │                             │  uow.__enter__()           │                     │
  │                             │ ──────────────────────────>│                     │
  │                             │                            │  BEGIN               │
  │                             │                            │ ───────────────────>│
  │                             │  handler(cmd, uow)         │                     │
  │                             │<═══════════════════════════│                     │
  │                             │                            │  uow.commit()        │
  │                             │                            │ ───────────────────>│
  │                             │                            │  COMMIT              │
  │                             │                            │ ───────────────────>│
  │                             │                            │  COLLECT EVENTS      │
  │                             │                            │  bus.handle(event)   │
  │                             │<═══════════════════════════│  FOR EACH EVENT      │
  │                             │  uow.__exit__()            │                     │
  │                             │<═══════════════════════════│                     │
```

---

## Unit of Work Pattern

```python
@contextmanager
def PostgresUnitOfWork(repo, connection_factory):
    connection = connection_factory()
    repo.attach(connection)
    yield self
    self.commit()

# Or class-based:
class PostgresUnitOfWork:
    def __init__(self, repo, connection_factory):
        self.repo = repo
        self._conn_factory = connection_factory
        self.events = []  # Collected domain events

    def __enter__(self):
        self.conn = self._conn_factory()
        self.repo.attach(self.conn)
        return self

    def __exit__(self, *args):
        self.conn.close()

    def commit(self):
        for aggregate in self.repo.seen:
            self.events.extend(aggregate.events)
        self.conn.commit()
```

---

## Existing File Migration Plan

Current files refactored to the new structure:

| Current File | New Home | Pattern Role |
|---|---|---|
| `backend/edge_engine/main.py` | `backend/engine/entrypoints/main.py` | Entrypoint (Cloud Run Job) |
| `backend/edge_engine/edge_detector.py` | `backend/engine/edge/edge_detector.py` | Pipelined algorithm (no patterns) |
| `backend/edge_engine/confidence_scorer.py` | `backend/engine/edge/confidence_scorer.py` | Pure function (no patterns) |
| `backend/edge_engine/stac_client.py` | `backend/engine/adapters/stac_client.py` | Adapter (external service) |
| `backend/edge_engine/models/schemas.py` | Split: `domain/models.py` + `domain/events.py` + `domain/commands.py` | Domain + messages |
| `backend/titiler/app.py` | `backend/titiler/app.py` (no change) | Read-side CQRS tile server |
| `backend/gdal_cog_processor/process.py` | `backend/gdal_cog_processor/process.py` (no change) | External pipeline |
