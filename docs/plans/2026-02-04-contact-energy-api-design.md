# Contact Energy Home Assistant Integration - Design

## Overview

A FastAPI server that proxies Contact Energy API data for Home Assistant consumption, with caching and SQLite storage for historical comparisons.

## Architecture

```
┌─────────────────┐     ┌─────────────────────────────────────────┐
│  Home Assistant │────▶│           FastAPI Server                │
│  (REST sensors) │     │                                         │
└─────────────────┘     │  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
                        │  │ Routes  │──│ Service │──│  Cache  │ │
                        │  └─────────┘  └────┬────┘  └─────────┘ │
                        │                    │                    │
                        │               ┌────▼────┐               │
                        │               │ SQLite  │               │
                        │               │   DB    │               │
                        │               └────┬────┘               │
                        └────────────────────┼────────────────────┘
                                             │
                                       ┌─────▼─────┐
                                       │  Contact  │
                                       │ Energy API│
                                       └───────────┘
```

## Key Decisions

| Aspect | Decision |
|--------|----------|
| Data scope | Monthly + hourly usage, both gas and electricity |
| Accounts | Discovery endpoint + query by contract ID |
| Authentication | Server-side credentials from .env only |
| API security | None (local network only) |
| Caching | 15-minute TTL in-memory cache |
| Storage | SQLite for historical data |
| Metrics | Raw data + aggregates + period/time comparisons |
| Deployment | Simple uvicorn |
| Structure | Modular (app/ package with routes/, services/, db/) |
| Testing | Unit tests with mocked API |

## File Structure

```
contact-energy-ha-integration/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app setup, lifespan events
│   ├── config.py            # Pydantic Settings (env vars)
│   ├── models.py            # Pydantic response models
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── accounts.py      # Account/contract discovery
│   │   ├── usage.py         # Usage data endpoints
│   │   └── health.py        # Health check endpoint
│   ├── services/
│   │   ├── __init__.py
│   │   ├── contact_api.py   # Wrapper around contact-energy-nz
│   │   ├── usage_service.py # Business logic, calculations
│   │   └── cache.py         # TTL cache implementation
│   └── db/
│       ├── __init__.py
│       ├── database.py      # SQLite connection/setup
│       └── repositories.py  # Data access layer
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Pytest fixtures, mocks
│   ├── test_routes.py
│   ├── test_services.py
│   └── test_repositories.py
├── main.py                   # Entry point (imports app.main)
├── pyproject.toml
├── .env
└── .gitignore
```

## API Endpoints

### Discovery

```
GET /health
  → {"status": "ok", "timestamp": "..."}

GET /accounts
  → [{"account_id": "123", "contracts": [
       {"contract_id": "456", "type": "electricity"},
       {"contract_id": "789", "type": "gas"}
     ]}]
```

### Usage Data (per contract)

```
GET /contracts/{contract_id}/usage/current
  → Current month summary with today's data

GET /contracts/{contract_id}/usage/hourly?date=2026-02-04
  → Hourly breakdown for specific day (defaults to today)

GET /contracts/{contract_id}/usage/monthly?start=2026-01&end=2026-02
  → Monthly usage for date range
```

### Calculated Metrics

```
GET /contracts/{contract_id}/summary
  → {
      "today": {"value": 12.5, "dollar_value": 3.20, ...},
      "yesterday": {"value": 15.2, ...},
      "this_month": {"value": 245.0, "daily_average": 8.5, ...},
      "last_month": {"value": 280.0, ...},
      "comparisons": {
        "vs_yesterday": -17.8,
        "vs_last_month": -12.5,
        "vs_same_day_last_week": 5.2
      }
    }
```

## Data Models

### Configuration (config.py)

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env')
    
    username: str                    # Contact Energy username
    password: str                    # Contact Energy password
    cache_ttl_minutes: int = 15      # How long to cache API responses
    database_path: str = "usage.db"  # SQLite database location
    host: str = "0.0.0.0"
    port: int = 8000
```

### Response Models (models.py)

```python
class UsageData(BaseModel):
    date: datetime
    value: float              # kWh or gas units
    unit: str                 # "kWh" or "units"
    dollar_value: float | None
    offpeak_value: float | None
    offpeak_dollar_value: float | None

class UsageSummary(BaseModel):
    today: UsageData | None
    yesterday: UsageData | None
    this_month: MonthlyAggregate
    last_month: MonthlyAggregate | None
    comparisons: Comparisons

class Contract(BaseModel):
    contract_id: str
    account_id: str
```

## Caching & Storage

### In-Memory Cache

- Uses `cachetools.TTLCache` (15-minute default)
- Cache keys: `accounts`, `usage:{contract_id}:{date}:{interval}`
- Cleared on startup; lightweight, no persistence needed

### SQLite Schema

```sql
CREATE TABLE usage_data (
    id INTEGER PRIMARY KEY,
    contract_id TEXT NOT NULL,
    date DATETIME NOT NULL,
    interval TEXT NOT NULL,  -- 'hourly' or 'monthly'
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    dollar_value REAL,
    offpeak_value REAL,
    offpeak_dollar_value REAL,
    uncharged_value REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(contract_id, date, interval)
);

CREATE INDEX idx_usage_lookup 
ON usage_data(contract_id, date, interval);
```

## Error Handling

| Scenario | Status | Response |
|----------|--------|----------|
| Success | 200 | Data payload |
| Contract not found | 404 | `{"detail": "Contract not found"}` |
| Invalid date range | 422 | Pydantic validation error |
| Contact Energy auth failed | 503 | `{"detail": "Upstream auth failed"}` |
| Contact Energy API error | 502 | `{"detail": "Upstream service error"}` |
| Rate limited by Contact | 429 | `{"detail": "Rate limited, try later"}` |

## Home Assistant Integration Example

```yaml
rest:
  - resource: http://192.168.1.100:8000/contracts/456/summary
    scan_interval: 300  # 5 minutes
    sensor:
      - name: "Electricity Today"
        value_template: "{{ value_json.today.value }}"
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: total_increasing
        
      - name: "Electricity Cost Today"
        value_template: "{{ value_json.today.dollar_value }}"
        unit_of_measurement: "NZD"
        
      - name: "Electricity vs Yesterday"
        value_template: "{{ value_json.comparisons.vs_yesterday }}"
        unit_of_measurement: "%"
        
      - name: "Monthly Usage"
        value_template: "{{ value_json.this_month.value }}"
        unit_of_measurement: "kWh"
```

## Dependencies

- `contact-energy-nz` - Contact Energy API client
- `fastapi` - Web framework
- `pydantic` - Data validation
- `pydantic-settings` - Environment configuration
- `cachetools` - TTL cache
- `aiosqlite` - Async SQLite
- `uvicorn` - ASGI server
- `pytest`, `pytest-asyncio`, `httpx` - Testing
