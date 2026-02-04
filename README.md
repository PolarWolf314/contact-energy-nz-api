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
- Today's usage
- Yesterday's usage
- This month's aggregate
- Last month's aggregate
- Comparisons (percentage changes)

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

## Home Assistant Configuration

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
        value_template: "{{ value_json.today.value | default('unavailable') }}"
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: total_increasing
        json_attributes:
          - today
          - yesterday
          - this_month
          - last_month
          - comparisons
          - contract_id
```

Replace:
- `YOUR_API_SERVER` with `127.0.0.1` or your server's IP
- `YOUR_CONTRACT_ID` with your contract ID from Step 1

### Step 5: Add Template Sensors

Add the following to your `configuration.yaml` (or create a separate `template.yaml` and include it):

```yaml
template:
  - sensor:
      # Today's Usage
      - name: "Electricity Today"
        unique_id: electricity_today
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: total_increasing
        icon: mdi:lightning-bolt
        state: >-
          {% set today = state_attr('sensor.contact_energy_summary', 'today') %}
          {{ today.value if today else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'today') is not none }}

      - name: "Electricity Today Cost"
        unique_id: electricity_today_cost
        unit_of_measurement: "$"
        device_class: monetary
        state_class: total_increasing
        icon: mdi:currency-usd
        state: >-
          {% set today = state_attr('sensor.contact_energy_summary', 'today') %}
          {{ today.dollar_value | round(2) if today else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'today') is not none }}

      # Yesterday's Usage
      - name: "Electricity Yesterday"
        unique_id: electricity_yesterday
        unit_of_measurement: "kWh"
        device_class: energy
        icon: mdi:lightning-bolt
        state: >-
          {% set yesterday = state_attr('sensor.contact_energy_summary', 'yesterday') %}
          {{ yesterday.value if yesterday else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'yesterday') is not none }}

      - name: "Electricity Yesterday Cost"
        unique_id: electricity_yesterday_cost
        unit_of_measurement: "$"
        device_class: monetary
        icon: mdi:currency-usd
        state: >-
          {% set yesterday = state_attr('sensor.contact_energy_summary', 'yesterday') %}
          {{ yesterday.dollar_value | round(2) if yesterday else 'unavailable' }}
        availability: >-
          {{ state_attr('sensor.contact_energy_summary', 'yesterday') is not none }}

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
      - name: "Electricity vs Yesterday"
        unique_id: electricity_vs_yesterday
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

## Available Sensors

After configuration, you'll have these sensors:

| Sensor | Description |
|--------|-------------|
| `sensor.contact_energy_summary` | Raw API data with all attributes |
| `sensor.electricity_today` | Today's usage in kWh |
| `sensor.electricity_today_cost` | Today's cost in $ |
| `sensor.electricity_yesterday` | Yesterday's usage in kWh |
| `sensor.electricity_yesterday_cost` | Yesterday's cost in $ |
| `sensor.electricity_this_month` | This month's total in kWh |
| `sensor.electricity_this_month_cost` | This month's cost in $ |
| `sensor.electricity_daily_average` | Daily average this month in kWh |
| `sensor.electricity_last_month` | Last month's total in kWh |
| `sensor.electricity_last_month_cost` | Last month's cost in $ |
| `sensor.electricity_vs_yesterday` | % change vs yesterday |
| `sensor.electricity_vs_last_week` | % change vs same day last week |
| `sensor.electricity_vs_last_month` | % change vs last month |

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
│   │   └── usage.py        # Usage data endpoints
│   └── services/
│       ├── cache.py        # TTL cache wrapper
│       ├── contact_api.py  # Contact Energy API client
│       └── usage_service.py # Business logic
├── homeassistant/
│   ├── rest_sensor.yaml    # REST sensor configuration
│   └── template_sensors.yaml # Template sensors configuration
├── tests/
│   ├── conftest.py         # Test fixtures
│   ├── test_repositories.py
│   ├── test_routes.py
│   └── test_services.py
├── contact-energy-api.service # systemd service file
├── main.py                 # Entry point
├── pyproject.toml
└── README.md
```

## License

MIT
