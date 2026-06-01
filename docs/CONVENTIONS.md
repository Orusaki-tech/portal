# Conventions

## Python

### Type Hints
- Use `from __future__ import annotations` in all `.py` files for deferred evaluation (Python 3.11+)
- Protocols for interfaces, ABC rarely
- `Optional[T]` for nullable values (not `T | None`)
- `list[T]`, `dict[K, V]` — lowercase generics (3.9+)
- `TypeVar` with bound constraints where applicable

```python
from __future__ import annotations
from typing import Protocol, Optional, TypeVar

T = TypeVar("T", bound="Aggregate")


class Repository(Protocol[T]):
    def add(self, aggregate: T) -> None: ...
    def get(self, id: UUID) -> Optional[T]: ...
```

### Imports (sorted)
1. `from __future__` (always first)
2. stdlib (`uuid`, `datetime`, `dataclasses`, `decimal`)
3. third-party (`psycopg2`, `numpy`, `shapely`)
4. local (`domain.models`, `service_layer.unit_of_work`)

One blank line between each group. No blank lines within groups.

### Data Classes & Immutability
- Value objects: `@dataclass(frozen=True)` — immutable, hashable
- Entities: `@dataclass` — mutable, identity-based equality (override `__eq__` with UUID comparison)
- Domain events: `@dataclass(frozen=True)` — immutable facts

```python
@dataclass(frozen=True)
class ConfidenceScore:
    overall: float
    per_vertex: list[VertexMetric]

    def __post_init__(self) -> None:
        assert 0.0 <= self.overall <= 1.0, "Confidence must be 0.0–1.0"
```

### Naming
| Construct | Convention | Example |
|---|---|---|
| Modules | `snake_case` | `unit_of_work.py`, `messagebus.py` |
| Classes | `PascalCase` | `TaskGrid`, `PostgresUnitOfWork` |
| Functions | `snake_case` | `handle_validate_polygon` |
| Commands | `PascalCase` (dataclass) | `ValidatePolygon`, `CorrectBoundary` |
| Events | `PascalCase` (past tense) | `PolygonValidated`, `BoundaryCorrected` |
| Handlers | `handle_<command/event>` | `handle_validate_polygon`, `handle_flag_for_review` |
| Tests | `test_<function>_<scenario>` | `test_validate_polygon_happy_path` |
| Fixtures | `fake_<repo_name>` | `fake_task_grid_repo` |

### Omit Comments
- Do NOT add comments to code unless the logic is genuinely non-obvious
- The domain model, handler names, and tests should be self-documenting
- Use docstrings only on Protocols and public APIs

---

## SQL

### Style
- Lowercase keywords (`select`, `from`, `where`, `insert into`)
- `snake_case` for all identifiers
- Explicit `as` aliases
- One column per line in `select` and `insert` lists
- `on delete cascade` for child tables
- Always include `if not exists` / `if exists`

```sql
insert into users (id, email, name, role, credits_remaining)
values
    (gen_random_uuid(), 'admin@realitysync.com', 'Admin', 'admin', 1000.00)
on conflict (email) do nothing;
```

### Geometry Columns
- Always specify SRID: `geometry(Polygon, 4326)`
- Always index with GIST: `create index on ml_polygons using gist (original_geometry)`
- Use `st_` functions, not `st_` abbreviation ambiguity
- Store in 4326 (WGS-84), reproject to 3857 for tile display

### Migrations
- One `.sql` file per migration
- Wrap in a transaction (PostgreSQL default)
- Add `comment on table` / `comment on column` for every table and column
- Idempotent: `create table if not exists`, `create index if not exists`

---

## Testing

### Structure
```
tests/
├── conftest.py           # Fixtures: fake repo, in-memory UoW, PostGIS container
├── unit/
│   ├── test_models.py    # Domain model invariants
│   ├── test_handlers.py  # Command/event handler tests (with fake repo)
│   └── test_bus.py       # Message bus routing
├── integration/
│   ├── test_repository.py    # PostgresTaskGridRepository with testcontainer
│   └── test_uow.py          # PostgresUnitOfWork commit/rollback
└── e2e/
    └── test_api.py           # Full round-trip via FastAPI test client
```

### Given/When/Then
```python
def test_validate_low_confidence_polygon_is_flagged() -> None:
    # Given
    repo = FakeTaskGridRepository()
    uow = FakeUnitOfWork(repo)
    polygon = Polygon(id=uuid4(), original_geometry=SAMPLE_POLYGON)
    repo.add(polygon)

    # When
    handle_validate_polygon(ValidatePolygon(polygon_id=polygon.id), uow)

    # Then
    assert polygon.qa_status == "low_confidence"
    assert len(uow.collected_events) == 1
    assert isinstance(uow.collected_events[0], LowConfidenceDetected)
```

### Fixtures
- `FakeTaskGridRepository` — `dict[UUID, TaskGrid]` in-memory, used for all unit tests
- `FakeUnitOfWork` — collects events but does nothing on `commit`
- `PostgresTestContainer` — `pytest` fixture using `testcontainers-postgres` for integration tests (mark with `@pytest.mark.integration`)

### Coverage
- Floor: 90% line coverage
- Critical: 100% on domain models (`models.py`, `events.py`, `commands.py`)
- Exemptions: `bootstrap.py`, `entrypoints/` (tested via E2E)

---

## Git & Commits

### Conventional Commits
```
feat:     New feature (e.g., "feat: add task grid row-locking")
fix:      Bug fix
refactor: Code restructuring with no behavior change
docs:     Documentation changes (in docs/ or docstrings)
db:       Database migration
test:     Test additions or changes
chore:    Build, CI, tooling
```

### Branch Naming
```
<phase>/<short-description>
# Examples:
phase-1/task-grid-aggregate
phase-2/edge-detection-notebook
phase-3/fastapi-setup
fix/confidence-scorer-div-zero
```

### PR Workflow
1. Branch from `main`
2. `git commit` with conventional message
3. Push → open PR against `main`
4. Required checks pass: `mypy --strict`, `pytest`, `ruff check`
5. At least one approval
6. Squash-merge to `main`

---

## dbt

### Model Naming

| Layer | Prefix | Materialization | Purpose |
|---|---|---|---|
| Staging | `stg_` | View | Raw → cleaned, column rename, type cast |
| Intermediate | `int_` | Ephemeral | Joins, metric computations |
| Marts | `fct_` / `dim_` | Table / Incremental | Business-facing facts + dimensions |

### Rules
- Always add `schema.yml` with column descriptions and tests for every model
- At minimum: `unique`, `not_null` on primary keys
- Never write raw SQL joins in marts — always reference `{{ ref('stg_*') }}`
- Use `source()` macros for raw database tables

### Testing
- Run `dbt test` before every commit that changes dbt models
- Custom test macros go in `dbt/macros/`
- Seed data in `dbt/seeds/` for reference tables (roles, status enums)
