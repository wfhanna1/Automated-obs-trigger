# Automated OBS Trigger

Serverless automation that starts and stops OBS Studio on remote Windows and Mac servers
according to a variable weekly schedule. Built on Azure Functions + Azure Service Bus.

## How it works

```
schedules/current_week.csv  (committed each week)
          │
          └─ GitHub Actions (auto on push)
                │
                └─► LoadSchedule Function  (HTTP)
                      │  reads CSV from GitHub
                      │  sends timed Service Bus messages
                      ▼
              Azure Service Bus  ("obs-jobs" queue)
              [holds messages until scheduled_enqueue_time_utc]
                      │
                      └─► OBSControl Function  (Service Bus trigger)
                            │  fires at exact start / stop time
                            │
                            ├─ SSH ──► Windows: Start-Process obs64.exe
                            │           └─ SSH tunnel → OBS WebSocket :4455
                            └─ SSH ──► Mac: nohup OBS.app
                                        └─ SSH tunnel → OBS WebSocket :4455
```

## Schedule format

Edit `schedules/current_week.csv` each week and push to `main`:

```csv
server_id,date,start_time,stop_time,action,timezone
win-server-1,2026-03-02,09:00,12:00,recording,America/New_York
win-server-2,2026-03-02,10:00,14:00,streaming,America/Chicago
mac-server-1,2026-03-03,10:00,15:00,recording,America/Los_Angeles
```

| Column | Description |
|---|---|
| `server_id` | Must match a key in `config/servers.yaml` |
| `date` | `YYYY-MM-DD` |
| `start_time` | `HH:MM` (24-hour, in the row's `timezone`) |
| `stop_time` | `HH:MM` (24-hour, in the row's `timezone`) |
| `action` | `recording` or `streaming` |
| `timezone` | IANA timezone string, e.g. `America/New_York`, `UTC` |

Lines starting with `#` are treated as comments and ignored.
Multiple rows per server per week are fully supported.

## Azure resources required

| Resource | SKU | Purpose |
|---|---|---|
| Azure Functions App | **Premium EP1** | Run both Functions with static outbound IPs |
| Azure Service Bus | Standard | `obs-jobs` queue with scheduled message support |
| Azure Key Vault | Standard | SSH private keys + OBS WebSocket passwords |
| Azure Storage Account | LRS | Functions runtime storage |

> **Why Premium EP1?** Static outbound IPs let you whitelist exactly which IPs can
> SSH into your remote servers, significantly reducing attack surface.

## Setup

### 1. Remote servers

**Windows (each machine):**
```powershell
# Install OpenSSH Server
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic

# Add your SSH public key
$authorizedKeysPath = "C:\ProgramData\ssh\administrators_authorized_keys"
Add-Content -Path $authorizedKeysPath -Value "<your-public-key>"
```

**Mac (each machine):**
- System Settings → Sharing → Remote Login: **On**
- Add your SSH public key to `~/.ssh/authorized_keys`

**OBS on all machines (Windows + Mac):**
- Install OBS Studio 28+ (WebSocket server is built in)
- Tools → WebSocket Server Settings → Enable, set port `4455`, set a strong password

### 2. Azure infrastructure

```bash
# Variables
RG=obs-scheduler-rg
LOCATION=eastus
SB_NS=obs-scheduler-sb
KV_NAME=obs-scheduler-kv
FUNC_STORAGE=obsschedulerstorage
FUNC_APP=obs-scheduler

# Resource Group
az group create -n $RG -l $LOCATION

# Service Bus + Queue
az servicebus namespace create -g $RG -n $SB_NS --sku Standard
az servicebus queue create -g $RG --namespace-name $SB_NS -n obs-jobs

# Storage Account (Functions runtime)
az storage account create -g $RG -n $FUNC_STORAGE --sku Standard_LRS

# Function App (Python 3.11, Premium EP1)
az functionapp create \
  -g $RG -n $FUNC_APP \
  --runtime python --runtime-version 3.11 \
  --storage-account $FUNC_STORAGE \
  --plan-sku EP1 --os-type Linux

# Enable system-assigned Managed Identity
az functionapp identity assign -g $RG -n $FUNC_APP

# Key Vault
az keyvault create -g $RG -n $KV_NAME
# Grant the Function App's identity access
FUNC_PRINCIPAL=$(az functionapp identity show -g $RG -n $FUNC_APP --query principalId -o tsv)
az keyvault set-policy -n $KV_NAME --object-id $FUNC_PRINCIPAL --secret-permissions get
```

### 3. Add secrets to Key Vault

For each server in `servers.yaml`, add two secrets:

```bash
SERVER_ID="win-server-1"        # replace with your server ID
KV_ID="${SERVER_ID//_/-}"       # Key Vault names use hyphens

# SSH private key (base64-encode the PEM file)
az keyvault secret set \
  --vault-name $KV_NAME \
  --name "ssh-key-${KV_ID}" \
  --value "$(cat ~/.ssh/your_server_key | base64 -w0)"

# OBS WebSocket password
az keyvault secret set \
  --vault-name $KV_NAME \
  --name "obs-ws-password-${KV_ID}" \
  --value "your_obs_websocket_password"
```

### 4. Configure Function App settings

```bash
SB_CONN=$(az servicebus namespace authorization-rule keys list \
  -g $RG --namespace-name $SB_NS -n RootManageSharedAccessKey \
  --query primaryConnectionString -o tsv)

KV_URI=$(az keyvault show -n $KV_NAME --query properties.vaultUri -o tsv)

az functionapp config appsettings set -g $RG -n $FUNC_APP --settings \
  "SERVICE_BUS_CONNECTION=$SB_CONN" \
  "GITHUB_RAW_CSV_URL=https://raw.githubusercontent.com/<org>/<repo>/main/schedules/current_week.csv" \
  "SERVERS_CONFIG_URL=https://raw.githubusercontent.com/<org>/<repo>/main/config/servers.yaml" \
  "KEY_VAULT_URI=$KV_URI"
```

### 5. Configure `config/servers.yaml`

Copy `config/servers.example.yaml` → `config/servers.yaml` and fill in your real values.
This file contains no secrets — only hostnames, usernames, and ports.

### 6. Deploy the Function App

```bash
func azure functionapp publish $FUNC_APP
```

Or set up GitHub Actions deployment (recommended for CI/CD).

### 7. Configure GitHub repository secrets

In your repo: **Settings → Secrets and variables → Actions**, add:

| Secret | Value |
|---|---|
| `AZURE_FUNCTION_BASE_URL` | `https://obs-scheduler.azurewebsites.net` |
| `AZURE_FUNCTION_KEY` | Function-level API key from Azure Portal |

### 8. Configure remote server firewalls

After deploying, get the Function App's static outbound IPs:
```bash
az functionapp show -g $RG -n $FUNC_APP --query outboundIpAddresses -o tsv
```

Whitelist only those IPs on port 22 (SSH) on each remote Windows/Mac server's firewall.

## Weekly usage

1. Fill in the Google Sheet / Excel template for the new week
2. Export as CSV, rename to `current_week.csv`
3. Commit and push:
   ```bash
   git add schedules/current_week.csv
   git commit -m "Schedule: week of 2026-03-09"
   git push
   ```
4. GitHub Actions automatically calls `LoadSchedule` → jobs are enqueued in Service Bus
5. At each scheduled time, `OBSControl` fires and starts/stops OBS on the correct server

## Local development

```bash
pip install -r requirements.txt

# Copy and fill in local settings
cp local.settings.json.example local.settings.json   # (create from host.json template)

# Start the local Functions runtime
func start
```

For local testing of the SSH/WebSocket modules directly:
```bash
python -c "
from src.remote_controller import obs_tunnel
from src.obs_websocket import start_action

KEY_PEM = open('~/.ssh/your_key').read()
with obs_tunnel('your-host', 22, 'admin', KEY_PEM, 4455) as port:
    start_action(port, 'your_obs_password', 'recording')
"
```

## Monitoring

All function executions are logged to **Azure Application Insights** (auto-configured with
the Function App). To view logs:
- Azure Portal → Function App → `obs_control_function` → Monitor
- Or: `func azure functionapp logstream $FUNC_APP`

To set up failure alerts:
- Azure Portal → Application Insights → Alerts → New alert rule
- Condition: `exceptions/count > 0` in the last 5 minutes

## Project structure

```
Automated-obs-trigger/
├── function_app.py              # Azure Functions: LoadSchedule + OBSControl
├── host.json                    # Functions host config (timeout, extensions)
├── requirements.txt             # Python dependencies
├── .github/
│   └── workflows/
│       └── load-schedule.yml    # Auto-trigger LoadSchedule on CSV push
├── config/
│   ├── servers.yaml             # Server configs (no secrets; gitignored)
│   └── servers.example.yaml    # Documented example
├── schedules/
│   ├── schedule_template.csv   # Blank template for weekly schedules
│   └── current_week.csv        # Active schedule (replace each week)
└── src/
    ├── schedule_loader.py       # CSV parser + validator
    ├── remote_controller.py     # SSH OBS launch/kill + tunnel context manager
    └── obs_websocket.py         # OBS WebSocket start/stop
```
