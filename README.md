# Parallel Log Analyzer

A distributed web log analytics platform using MPI for parallel processing. Each MPI worker represents a web server with its own access log, while rank 0 aggregates insights. Includes a full-featured web dashboard for visualization.

---

## Features

- **MPI Parallel Processing**: Head/worker architecture for scalable log analysis
- **Realistic Log Generation**: Imbalanced traffic patterns per server (region weights, peak hours)
- **Comprehensive Analytics**: Status codes, methods, regions, hourly traffic, top paths
- **Interactive Dashboard**: 6-page web UI with light/dark theme, per-chart filters, real-time updates

---

## Prerequisites

### Windows
1. **Python 3.10+**: Download from [python.org](https://www.python.org/downloads/)
2. **Microsoft MPI v10.1.3+**: Download from [Microsoft MPI](https://learn.microsoft.com/en-us/message-passing-interface/microsoft-mpi)
   - Install the runtime (`msmpisetup.exe`)
   - Restart your terminal after installation so `mpiexec` is on PATH

### Linux/macOS
```bash
# Ubuntu/Debian
sudo apt install mpich python3-pip

# macOS with Homebrew
brew install mpich
```

---

## Installation

```powershell
# Clone or navigate to the project
cd C:\parallel_log_analyzer

# Create virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Or on Linux/macOS
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Dependencies** (`requirements.txt`):
- `mpi4py>=3.1` – MPI bindings for Python
- `matplotlib>=3.7` – Static plot generation
- `flask>=2.3` – Web dashboard server

---

## Quick Start

### 1. Generate Sample Logs

```powershell
python generate_logs.py --servers 3 --rows 5000
```

This creates realistic, imbalanced logs in `logs/`:
| Server | Profile | Traffic | Peak Hours (UTC) |
|--------|---------|---------|------------------|
| server1 | US/API heavy | 120% base | 9:00–17:00 |
| server2 | EU/E-commerce | 100% base | 10:00–20:00 |
| server3 | Asia/Admin | 70% base | 0:00–8:00 |

### 2. Run Parallel Analysis

```powershell
mpiexec -n 4 python parallel_analyzer.py ^
    --logs logs/server1.log logs/server2.log logs/server3.log ^
    --output reports/parallel_summary.json ^
    --plot plots/summary.png
```

> **Note**: MPI world size = number of logs + 1 (head). For 3 logs, use `-n 4`.

### 3. Launch the Dashboard

```powershell
python dashboard.py ^
    --summary reports/parallel_summary.json ^
    --logs-dir logs ^
    --port 8000
```

Open **http://127.0.0.1:8000** in your browser.

---

## Dashboard Features

### Navigation (Sidebar)
| Page | Description |
|------|-------------|
| **Overview** | Stats grid, requests/errors/hourly/methods charts |
| **Servers** | Deep-dive into individual server metrics |
| **Traffic** | Multi-server traffic comparison, volume, bytes |
| **Geography** | Regional distribution (global & per-server) |
| **Errors** | Status code breakdown, error rates |
| **Paths** | Top URLs with search filter |
| **Raw Logs** | Browse actual log entries with filters |

### Key Features
- **Light/Dark Theme**: Toggle in sidebar footer (persists in browser)
- **Per-Chart Filters**: Change chart types, filter by server/region
- **Real-time Updates**: Auto-refreshes when analysis JSON changes (via SSE)
- **Responsive Design**: Works on desktop and tablet

### API Endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /` | Main dashboard UI |
| `GET /api/summary` | Full analysis JSON |
| `GET /api/meta` | Available servers and regions |
| `GET /api/servers` | All server summaries |
| `GET /api/server/<name>` | Single server details |
| `GET /api/timeseries` | Hourly traffic data |
| `GET /api/top-paths?server=X&k=10` | Top paths |
| `GET /api/raw?server=X&status_class=5&method=GET` | Raw log entries |
| `GET /api/stream` | Server-Sent Events for live updates |

---

## Project Structure

```
parallel_log_analyzer/
├── analysis_core.py      # Shared parsing & statistics utilities
├── generate_logs.py      # Realistic multi-server log generator
├── parallel_analyzer.py  # MPI head/worker analyzer
├── dashboard.py          # Flask web dashboard
├── requirements.txt      # Python dependencies
├── logs/                 # Generated log files
│   ├── server1.log
│   ├── server2.log
│   └── server3.log
├── reports/              # Analysis output
│   └── parallel_summary.json
└── plots/                # Generated visualizations
    └── summary.png
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        MPI World                            │
├─────────────┬─────────────┬─────────────┬─────────────┬─────┤
│   Rank 0    │   Rank 1    │   Rank 2    │   Rank 3    │ ... │
│   (Head)    │  (Worker)   │  (Worker)   │  (Worker)   │     │
│             │             │             │             │     │
│  Aggregate  │  server1    │  server2    │  server3    │     │
│  & Report   │    .log     │    .log     │    .log     │     │
└──────▲──────┴──────┬──────┴──────┬──────┴──────┬──────┴─────┘
       │             │             │             │
       └─────────────┴─────────────┴─────────────┘
                   MPI Gather (summaries)
```

**Data Flow**:
1. Each worker loads its assigned server log
2. Computes local stats (requests, errors, regions, paths, hourly)
3. Sends compact summary to head via MPI gather
4. Head merges all summaries, derives rankings, writes JSON/plot

---

## Metrics Computed

### Per Server
- Total requests & bytes
- Error rate (4xx + 5xx / total)
- Status code breakdown (200, 404, 500, etc.)
- HTTP method breakdown (GET, POST, PUT, DELETE)
- Top 10 paths by hit count
- Region distribution (North America, Europe, Asia, Africa, Other)
- Hourly histogram (0–23)
- Peak hour

### Global (Aggregated)
- Merged totals from all servers
- Busiest server (by request count)
- Highest error server (by error rate)

---

## Log Format

Logs follow the Common Log Format:
```
IP - - [DD/Mon/YYYY:HH:MM:SS +0000] "METHOD PATH HTTP/1.1" STATUS BYTES
```

Example:
```
192.168.1.45 - - [15/Mar/2025:14:32:01 +0000] "GET /api/users HTTP/1.1" 200 1234
```

### Region Mapping (by IP first octet)
| First Octet | Region |
|-------------|--------|
| 1–49 | North America |
| 50–99 | Europe |
| 100–149 | Asia |
| 150–199 | Africa |
| 200+ | Other |

---

## Command Reference

### generate_logs.py
```
python generate_logs.py [OPTIONS]

Options:
  --servers N       Number of server logs to generate (default: 3)
  --rows N          Base rows per server (default: 1000)
  --output-dir DIR  Output directory (default: logs)
```

### parallel_analyzer.py
```
mpiexec -n <N+1> python parallel_analyzer.py [OPTIONS]

Options:
  --logs FILE [FILE ...]  Log files to analyze (one per worker)
  --output FILE           Output JSON path (default: reports/parallel_summary.json)
  --plot FILE             Optional plot output path
```

### dashboard.py
```
python dashboard.py [OPTIONS]

Options:
  --summary FILE    Path to analysis JSON (default: reports/parallel_summary.json)
  --logs-dir DIR    Directory with raw logs for browsing (optional)
  --plot FILE       Path to plot image (optional)
  --host HOST       Bind address (default: 127.0.0.1)
  --port PORT       Bind port (default: 8000)
```

---

## Troubleshooting

### "mpiexec is not recognized"
- Ensure Microsoft MPI is installed
- Restart your terminal/IDE after installation
- Verify with: `mpiexec -help`

### "ModuleNotFoundError: No module named 'mpi4py'"
- Activate your virtual environment first:
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```

### Dashboard shows "Failed to load data"
- Ensure `reports/parallel_summary.json` exists
- Run the parallel analyzer first

### Logs not showing in Raw Logs view
- Pass `--logs-dir logs` when starting the dashboard

---

## License

MIT License - See [LICENSE](LICENSE) for details.
