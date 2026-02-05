# Contact Energy Home Assistant Integration

A FastAPI server that proxies Contact Energy usage data for Home Assistant integration, with an optional HACS-compatible custom component for deeper integration.

## Features

- Fetches electricity and gas usage data from Contact Energy NZ
- Exposes REST API endpoints suitable for Home Assistant REST sensors
- **HACS-compatible custom component** for native Home Assistant integration
- Caches responses (15-minute TTL) to reduce API calls
- Stores historical data in SQLite for comparisons
- Provides usage comparisons (vs yesterday, vs last month, vs same day last week)
- **Adaptive backfill** - fetches ALL available historical data from Contact Energy
- **Historical statistics import** - imports data into HA's long-term statistics for Energy Dashboard

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Contact Energy NZ account credentials
- Linux server (Ubuntu recommended) for production deployment

## Quick Start

```bash
# Clone the repository
git clone <repository-url>
cd contact-energy-ha-integration

# Install dependencies
uv sync

# Create .env file with your credentials
cat > .env << 'EOF'
USERNAME=your_contact_energy_email
PASSWORD=your_contact_energy_password
EOF

# Start the server
uv run python main.py
```

The API will be available at `http://localhost:8000`.

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

# Backfill settings
BACKFILL_MAX_DAYS=0          # 0 = adaptive (unlimited), or specify max days
BACKFILL_EMPTY_DAYS_THRESHOLD=3  # Stop after this many consecutive empty days
BACKFILL_API_DELAY=1.0       # Seconds between API calls (rate limiting)

# Sync settings
REGULAR_SYNC_DAYS=7          # Days of hourly data to sync on regular sync
REGULAR_SYNC_MONTHS=2        # Months of monthly data to sync on regular sync
SYNC_INTERVAL_MINUTES=15     # Background sync interval
```

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

Returns all accounts and contracts associated with your Contact Energy login. Use this to find your contract ID.

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
- Latest day's usage (typically 3-4 days behind real-time)
- Previous day's usage
- This month's aggregate
- Last month's aggregate
- Comparisons (percentage changes)
- `data_as_of` field showing the date of the most recent data

**Note:** Contact Energy data is typically delayed by 3-4 days. The API provides `latest_day` and `previous_day` fields with actual dates rather than assuming "today" data is available.

### Sync Endpoints

```
POST /sync
```

Trigger a manual sync. Optional query params:
- `days`: Number of days to sync (default: 7, max: 365)
- `months`: Number of months to sync (default: 2)

```
POST /sync/backfill/adaptive
```

Trigger a full adaptive backfill that fetches ALL available historical data.
Stops when the API returns 3 consecutive days with no data.

```
GET /sync/status
```

Returns current sync status and backfill progress.

### Contract Stats

```
GET /contracts/{contract_id}/stats
```

Returns database statistics including oldest/newest records and counts.

---

## Production Deployment (Ubuntu/Linux)

### Step 1: Clone and Configure

```bash
# Clone to your preferred location
cd /home/YOUR_USER/developer
git clone <repository-url> contact-energy-api
cd contact-energy-api

# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Install dependencies
uv sync

# Create .env file
cat > .env << 'EOF'
USERNAME=your_contact_energy_email
PASSWORD=your_contact_energy_password
EOF
```

### Step 2: Test the Server

```bash
# Start the server manually
uv run python main.py

# In another terminal, test it
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/accounts  # Note your contract_id from the response

# Stop with Ctrl+C
```

### Step 3: Configure systemd Service

Edit the included service file to match your setup:

```bash
# Edit the service file
nano contact-energy-api.service
```

Update these lines to match your environment:
- `User=YOUR_USER`
- `WorkingDirectory=/home/YOUR_USER/developer/contact-energy-api`
- `ExecStart=/home/YOUR_USER/.local/bin/uv run python main.py`
- `Environment=PATH=/home/YOUR_USER/.local/bin:/usr/local/bin:/usr/bin:/bin`

Install and enable the service:

```bash
sudo cp contact-energy-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable contact-energy-api
sudo systemctl start contact-energy-api
```

### Step 4: Verify the Service

```bash
# Check status
sudo systemctl status contact-energy-api

# View logs
sudo journalctl -u contact-energy-api -f

# Test the API
curl http://127.0.0.1:8000/health
```

### Managing the Service

```bash
# Stop the service
sudo systemctl stop contact-energy-api

# Restart the service
sudo systemctl restart contact-energy-api

# View recent logs
sudo journalctl -u contact-energy-api --since "1 hour ago"
```

---

## Home Assistant Integration Options

There are two ways to integrate with Home Assistant:

1. **Custom Component (Recommended)** - HACS-compatible native integration with automatic statistics import
2. **REST Sensors** - Manual configuration using Home Assistant's built-in REST platform

### Architecture Overview

This integration uses a **two-component architecture**:

```
┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│   Contact Energy    │      │   FastAPI Server    │      │   Home Assistant    │
│        API          │◄────►│   (this project)    │◄────►│   Custom Component  │
│                     │      │   Port 8000         │      │   (HACS)            │
└─────────────────────┘      └─────────────────────┘      └─────────────────────┘
```

**Why two components?**

The Contact Energy API requires complex browser-like authentication (cookies, tokens, redirects). Rather than embedding this complexity into a Home Assistant integration, the FastAPI server handles the auth and data storage, while the HA component consumes clean REST endpoints.

**This means you need:**
1. The **FastAPI server running** (via systemd, Docker, or manually) - handles Contact Energy auth and data sync
2. The **HACS component installed** in Home Assistant - connects to YOUR server, not Contact Energy directly

**Deployment options:**
- Run the server on the **same machine** as Home Assistant
- Run the server on a **separate machine** on your network
- The server URL is configurable during HACS component setup

---

## Option 1: HACS Custom Component (Recommended)

**Prerequisites:** The FastAPI server must be running and accessible from Home Assistant. Complete the [Production Deployment](#production-deployment-ubuntulinux) section first.

The custom component provides the best experience with:
- Native Home Assistant integration with UI-based setup
- Automatic discovery of all your Contact Energy contracts
- Historical data import into HA's long-term statistics
- Energy Dashboard compatibility out of the box
- Services for manual sync and backfill

### Installation via HACS

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant
2. Go to **HACS** > **Integrations**
3. Click the three dots menu (top right) > **Custom repositories**
4. Add this repository URL with category "Integration"
5. Click **Install** on "Contact Energy"
6. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/contact_energy` folder to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

### Configuration

1. Go to **Settings** > **Devices & Services**
2. Click **Add Integration**
3. Search for "Contact Energy"
4. Enter your API server URL (e.g., `http://192.168.1.100:8000`)
5. The integration will automatically discover all your contracts

### Available Sensors

The integration creates these sensors for each contract:

**Electricity Contracts:**
| Sensor | Description |
|--------|-------------|
| `sensor.contact_energy_XXXXX_latest_day_energy` | Latest available day's usage in kWh |
| `sensor.contact_energy_XXXXX_latest_day_cost` | Latest available day's cost in $ |
| `sensor.contact_energy_XXXXX_previous_day_energy` | Previous day's usage in kWh |
| `sensor.contact_energy_XXXXX_previous_day_cost` | Previous day's cost in $ |
| `sensor.contact_energy_XXXXX_data_as_of` | Date of the most recent data |
| `sensor.contact_energy_XXXXX_this_month_energy` | This month's total in kWh |
| `sensor.contact_energy_XXXXX_this_month_cost` | This month's cost in $ |
| `sensor.contact_energy_XXXXX_daily_average` | Daily average this month in kWh |
| `sensor.contact_energy_XXXXX_vs_previous_day` | % change vs previous day |
| `sensor.contact_energy_XXXXX_vs_last_month` | % change vs last month |

**Note:** Contact Energy data is typically 3-4 days delayed. The "Latest Day" sensor shows the most recent day with data, and the "Data As Of" sensor shows the actual date.

**Gas Contracts:**
| Sensor | Description |
|--------|-------------|
| `sensor.contact_energy_XXXXX_gas_this_month` | This month's gas usage |
| `sensor.contact_energy_XXXXX_gas_this_month_cost` | This month's gas cost |

### Services

The integration provides these services:

- `contact_energy.sync` - Trigger a manual sync
- `contact_energy.backfill` - Run adaptive backfill to fetch all historical data
- `contact_energy.import_statistics` - Import historical data into HA statistics

### Energy Dashboard

The sensors are automatically configured with the correct `state_class` and `device_class` for the Energy Dashboard. After installation:

1. Go to **Settings** > **Dashboards** > **Energy**
2. Under "Electricity grid", click **Add consumption**
3. Select `sensor.contact_energy_XXXXX_latest_day_energy`

Historical data is automatically imported into long-term statistics, so your Energy Dashboard will show historical data immediately.

---

## Option 2: REST Sensors (Manual Configuration)

If you prefer not to use the custom component, you can configure REST sensors manually.

### Step 1: Find Your Contract ID

After starting the API server, call the accounts endpoint:

```bash
curl http://YOUR_SERVER_IP:8000/accounts
```

Note your `contract_id` from the response.

### Step 2: Determine the API URL

- If Home Assistant runs on the **same machine** as the API, or uses Docker with `--network=host`:
  - Use `http://127.0.0.1:8000`
- If Home Assistant uses Docker with **bridge networking**:
  - Use your server's LAN IP, e.g., `http://192.168.1.100:8000`
  - Find your IP with: `ip addr show | grep "inet " | grep -v 127.0.0.1`

### Step 3: Access Home Assistant Configuration Files

Since Home Assistant Container doesn't include a file editor by default, you have several options:

**Option A: Edit files directly on the host**

Your Home Assistant config directory is mounted from your host. Find it and edit directly:

```bash
# Common locations:
# /home/YOUR_USER/homeassistant/configuration.yaml
# /opt/homeassistant/configuration.yaml
# Check your docker-compose.yml or docker run command for the volume mount

nano /path/to/your/homeassistant/configuration.yaml
```

**Option B: Install File Editor (Recommended)**

If you want to edit files from the HA web interface, you can install the File Editor as a standalone container or use VS Code Server. However, for HA Container installations, editing directly on the host is typically easier.

### Step 4: Add REST Sensor

Add the following to your `configuration.yaml`:

```yaml
rest:
  - resource: http://YOUR_API_SERVER:8000/contracts/YOUR_CONTRACT_ID/summary
    scan_interval: 900  # 15 minutes
    sensor:
      - name: "Contact Energy Summary"
        unique_id: contact_energy_summary
        value_template: "{{ value_json.latest_day.value | default('unavailable') }}"
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: total_increasing
        json_attributes:
          - latest_day
          - previous_day
          - this_month
          - last_month
          - comparisons
          - data_as_of
          - contract_id
```

Replace:
- `YOUR_API_SERVER` with `127.0.0.1` or your server's IP
- `YOUR_CONTRACT_ID` with your contract ID from Step 1

**Note:** Contact Energy data is typically 3-4 days delayed. The `latest_day` and `previous_day` attributes contain the actual dates of the data.

### Step 5: Add Template Sensors

Add the following to your `configuration.yaml` (or create a separate `template.yaml` and include it):

```yaml
template:
  - sensor:
      # Data freshness indicator
      - name: "Electricity Data As Of"
        unique_id: electricity_data_as_of
        icon: mdi:calendar-clock
        state: >-
          {{ state_attr('sensor.contact_energy_summary', 'data_as_of') | default('unavailable') }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'data_as_of') is not none }}

      # Latest Day's Usage (most recent data available)
      - name: "Electricity Latest Day"
        unique_id: electricity_latest_day
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: total_increasing
        icon: mdi:lightning-bolt
        state: >-
          {% set latest = state_attr('sensor.contact_energy_summary', 'latest_day') %}
          {{ latest.value if latest else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'latest_day') is not none }}

      - name: "Electricity Latest Day Cost"
        unique_id: electricity_latest_day_cost
        unit_of_measurement: "$"
        device_class: monetary
        state_class: total_increasing
        icon: mdi:currency-usd
        state: >-
          {% set latest = state_attr('sensor.contact_energy_summary', 'latest_day') %}
          {{ latest.dollar_value | round(2) if latest else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'latest_day') is not none }}

      # Previous Day's Usage
      - name: "Electricity Previous Day"
        unique_id: electricity_previous_day
        unit_of_measurement: "kWh"
        device_class: energy
        icon: mdi:lightning-bolt
        state: >-
          {% set previous = state_attr('sensor.contact_energy_summary', 'previous_day') %}
          {{ previous.value if previous else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'previous_day') is not none }}

      - name: "Electricity Previous Day Cost"
        unique_id: electricity_previous_day_cost
        unit_of_measurement: "$"
        device_class: monetary
        icon: mdi:currency-usd
        state: >-
          {% set previous = state_attr('sensor.contact_energy_summary', 'previous_day') %}
          {{ previous.dollar_value | round(2) if previous else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'previous_day') is not none }}

      # This Month's Usage
      - name: "Electricity This Month"
        unique_id: electricity_this_month
        unit_of_measurement: "kWh"
        device_class: energy
        icon: mdi:calendar-month
        state: >-
          {% set this_month = state_attr('sensor.contact_energy_summary', 'this_month') %}
          {{ this_month.value | round(2) if this_month else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'this_month') is not none }}

      - name: "Electricity This Month Cost"
        unique_id: electricity_this_month_cost
        unit_of_measurement: "$"
        device_class: monetary
        icon: mdi:currency-usd
        state: >-
          {% set this_month = state_attr('sensor.contact_energy_summary', 'this_month') %}
          {{ this_month.dollar_value | round(2) if this_month else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'this_month') is not none }}

      - name: "Electricity Daily Average"
        unique_id: electricity_daily_average
        unit_of_measurement: "kWh"
        device_class: energy
        icon: mdi:chart-line
        state: >-
          {% set this_month = state_attr('sensor.contact_energy_summary', 'this_month') %}
          {{ this_month.daily_average | round(2) if this_month else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'this_month') is not none }}

      # Last Month's Usage
      - name: "Electricity Last Month"
        unique_id: electricity_last_month
        unit_of_measurement: "kWh"
        device_class: energy
        icon: mdi:calendar-month-outline
        state: >-
          {% set last_month = state_attr('sensor.contact_energy_summary', 'last_month') %}
          {{ last_month.value | round(2) if last_month else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'last_month') is not none }}

      - name: "Electricity Last Month Cost"
        unique_id: electricity_last_month_cost
        unit_of_measurement: "$"
        device_class: monetary
        icon: mdi:currency-usd
        state: >-
          {% set last_month = state_attr('sensor.contact_energy_summary', 'last_month') %}
          {{ last_month.dollar_value | round(2) if last_month else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'last_month') is not none }}

      # Comparisons
      - name: "Electricity vs Previous Day"
        unique_id: electricity_vs_previous_day
        unit_of_measurement: "%"
        icon: mdi:percent
        state: >-
          {% set comparisons = state_attr('sensor.contact_energy_summary', 'comparisons') %}
          {{ comparisons.vs_yesterday | round(1) if comparisons and comparisons.vs_yesterday is not none else 'unavailable' }}
        availability: >-
          {% set comparisons = state_attr('sensor.contact_energy_summary', 'comparisons') %}
          {{ comparisons is not none and comparisons.vs_yesterday is not none }}

      - name: "Electricity vs Last Week"
        unique_id: electricity_vs_last_week
        unit_of_measurement: "%"
        icon: mdi:percent
        state: >-
          {% set comparisons = state_attr('sensor.contact_energy_summary', 'comparisons') %}
          {{ comparisons.vs_same_day_last_week | round(1) if comparisons and comparisons.vs_same_day_last_week is not none else 'unavailable' }}
        availability: >-
          {% set comparisons = state_attr('sensor.contact_energy_summary', 'comparisons') %}
          {{ comparisons is not none and comparisons.vs_same_day_last_week is not none }}

      - name: "Electricity vs Last Month"
        unique_id: electricity_vs_last_month
        unit_of_measurement: "%"
        icon: mdi:percent
        state: >-
          {% set comparisons = state_attr('sensor.contact_energy_summary', 'comparisons') %}
          {{ comparisons.vs_last_month | round(1) if comparisons and comparisons.vs_last_month is not none else 'unavailable' }}
        availability: >-
          {% set comparisons = state_attr('sensor.contact_energy_summary', 'comparisons') %}
          {{ comparisons is not none and comparisons.vs_last_month is not none }}
```

You can also copy the pre-made configuration files from the `homeassistant/` directory in this repository.

### Step 6: Validate and Restart Home Assistant

**Validate configuration:**

1. In Home Assistant, go to **Developer Tools** (bottom left menu)
2. Click the **YAML** tab
3. Click **CHECK CONFIGURATION**
4. Fix any errors shown

**Restart Home Assistant:**

```bash
# If using docker-compose
docker compose restart homeassistant

# Or if using docker run
docker restart homeassistant
```

Or from the HA web interface:
1. Go to **Settings** > **System** > **Restart**

### Step 7: Verify Sensors

1. Go to **Developer Tools** > **States**
2. Search for `contact_energy` or `electricity`
3. You should see all the sensors with their values

---

## Available Sensors (REST Configuration)

After configuration, you'll have these sensors:

| Sensor | Description |
|--------|-------------|
| `sensor.contact_energy_summary` | Raw API data with all attributes |
| `sensor.electricity_data_as_of` | Date of the most recent data |
| `sensor.electricity_latest_day` | Latest day's usage in kWh |
| `sensor.electricity_latest_day_cost` | Latest day's cost in $ |
| `sensor.electricity_previous_day` | Previous day's usage in kWh |
| `sensor.electricity_previous_day_cost` | Previous day's cost in $ |
| `sensor.electricity_this_month` | This month's total in kWh |
| `sensor.electricity_this_month_cost` | This month's cost in $ |
| `sensor.electricity_daily_average` | Daily average this month in kWh |
| `sensor.electricity_last_month` | Last month's total in kWh |
| `sensor.electricity_last_month_cost` | Last month's cost in $ |
| `sensor.electricity_vs_previous_day` | % change vs previous day |
| `sensor.electricity_vs_last_week` | % change vs same day last week |
| `sensor.electricity_vs_last_month` | % change vs last month |

**Note:** Contact Energy data is typically 3-4 days delayed. Check the `electricity_data_as_of` sensor to see the actual date of the latest data.

---

## Troubleshooting

### API Server Issues

```bash
# Check if the service is running
sudo systemctl status contact-energy-api

# View logs
sudo journalctl -u contact-energy-api -f

# Test the API directly
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/contracts/YOUR_CONTRACT_ID/summary
```

### Home Assistant Issues

1. Check HA logs: **Settings** > **System** > **Logs**
2. Search for "rest" or "contact_energy" errors
3. Verify the API is reachable from the HA container:
   ```bash
   docker exec -it homeassistant curl http://YOUR_API_SERVER:8000/health
   ```

### Common Problems

**"unavailable" state:**
- The API might not have data for today yet (Contact Energy data can be delayed)
- Check the API response directly to see what data is available

**Connection refused:**
- Verify the API server is running
- Check firewall settings if HA is on a different machine
- Verify the correct IP address is being used

---

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
│   │   ├── sync.py         # Sync and backfill endpoints
│   │   └── usage.py        # Usage data endpoints
│   └── services/
│       ├── cache.py        # TTL cache wrapper
│       ├── contact_api.py  # Contact Energy API client
│       ├── sync.py         # Sync and backfill logic
│       └── usage_service.py # Business logic
├── custom_components/
│   └── contact_energy/     # Home Assistant custom component
│       ├── __init__.py     # Integration setup
│       ├── config_flow.py  # UI configuration flow
│       ├── const.py        # Constants
│       ├── coordinator.py  # Data update coordinator
│       ├── manifest.json   # HACS manifest
│       ├── sensor.py       # Sensor entities
│       ├── services.yaml   # Service definitions
│       └── strings.json    # Translations
├── homeassistant/
│   ├── rest_sensor.yaml    # REST sensor configuration
│   └── template_sensors.yaml # Template sensors configuration
├── tests/
│   ├── conftest.py         # Test fixtures
│   ├── test_repositories.py
│   ├── test_routes.py
│   └── test_services.py
├── contact-energy-api.service # systemd service file
├── hacs.json               # HACS repository configuration
├── main.py                 # Entry point
├── pyproject.toml
└── README.md
```

## License

MIT
