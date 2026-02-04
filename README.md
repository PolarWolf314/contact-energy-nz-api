# Contact Energy Home Assistant Integration

A FastAPI server that proxies Contact Energy usage data for Home Assistant integration.

## Features

- Fetches electricity usage data from Contact Energy NZ
- Exposes REST API endpoints suitable for Home Assistant REST sensors
- Caches responses (15-minute TTL) to reduce API calls
- Stores historical data in SQLite for comparisons
- Provides usage comparisons (vs yesterday, vs last month, vs same day last week)

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Contact Energy NZ account credentials

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd contact-energy-ha-integration

# Install dependencies
uv sync
```

## Configuration

Create a `.env` file in the project root:

```env
USERNAME=your_contact_energy_email
PASSWORD=your_contact_energy_password
```

Optional settings (with defaults):

```env
DATABASE_PATH=usage.db
CACHE_TTL=900
```

## Usage

Start the server:

```bash
uv run python main.py
```

The API will be available at `http://localhost:8000`.

## API Endpoints

### Health Check

```
GET /health
```

Returns server status.

### Discover Accounts

```
GET /accounts
```

Returns all accounts and contracts associated with your Contact Energy login.

### Current Usage

```
GET /contracts/{contract_id}/usage/current
```

Returns current month's aggregate usage and today's usage so far.

### Hourly Usage

```
GET /contracts/{contract_id}/usage/hourly?date=YYYY-MM-DD
```

Returns hourly breakdown for a specific day. Defaults to today if no date provided.

### Monthly Usage

```
GET /contracts/{contract_id}/usage/monthly?start=YYYY-MM&end=YYYY-MM
```

Returns monthly aggregates for a date range.

### Usage Summary (Recommended for Home Assistant)

```
GET /contracts/{contract_id}/summary
```

Returns a complete summary including:
- Today's usage
- Yesterday's usage
- This month's aggregate
- Last month's aggregate
- Comparisons (percentage changes)

## Home Assistant Configuration

Add REST sensors to your `configuration.yaml`:

```yaml
sensor:
  - platform: rest
    name: Contact Energy Usage
    resource: http://localhost:8000/contracts/YOUR_CONTRACT_ID/summary
    scan_interval: 900  # 15 minutes
    json_attributes:
      - today
      - yesterday
      - this_month
      - last_month
      - comparisons
    value_template: "{{ value_json.today.value if value_json.today else 'N/A' }}"
    unit_of_measurement: "kWh"

  - platform: template
    sensors:
      electricity_today:
        friendly_name: "Electricity Today"
        unit_of_measurement: "kWh"
        value_template: "{{ state_attr('sensor.contact_energy_usage', 'today').value | default('N/A') }}"
      
      electricity_today_cost:
        friendly_name: "Electricity Today Cost"
        unit_of_measurement: "$"
        value_template: "{{ state_attr('sensor.contact_energy_usage', 'today').dollar_value | default('N/A') }}"
      
      electricity_vs_yesterday:
        friendly_name: "Electricity vs Yesterday"
        unit_of_measurement: "%"
        value_template: "{{ state_attr('sensor.contact_energy_usage', 'comparisons').vs_yesterday | default('N/A') }}"
```

## Development

Run tests:

```bash
uv run pytest
```

Run tests with coverage:

```bash
uv run pytest --cov=app
```

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── config.py           # Settings from environment
│   ├── main.py             # FastAPI application
│   ├── models.py           # Pydantic response models
│   ├── db/
│   │   ├── database.py     # SQLite connection manager
│   │   └── repositories.py # Data access layer
│   ├── routes/
│   │   ├── accounts.py     # Account discovery endpoint
│   │   ├── health.py       # Health check endpoint
│   │   └── usage.py        # Usage data endpoints
│   └── services/
│       ├── cache.py        # TTL cache wrapper
│       ├── contact_api.py  # Contact Energy API client
│       └── usage_service.py # Business logic
├── tests/
│   ├── conftest.py         # Test fixtures
│   ├── test_repositories.py
│   ├── test_routes.py
│   └── test_services.py
├── main.py                 # Entry point
├── pyproject.toml
└── README.md
```

## License

MIT
