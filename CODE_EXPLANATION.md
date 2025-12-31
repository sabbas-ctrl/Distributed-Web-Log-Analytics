# Complete Code Explanation - Line by Line

## 1. PARALLEL_ANALYZER.PY

This is the MPI orchestrator that manages distributed log processing across multiple worker processes.

### Imports (Lines 1-8)
```python
import argparse           # For parsing command-line arguments
import json              # For reading/writing JSON files
import os               # For file system operations
from pathlib import Path  # Modern file path handling

from mpi4py import MPI   # MPI (Message Passing Interface) library for distributed computing
from analysis_core import ...  # Imports utility functions from analysis_core.py
```

### Function: `analyze_file()` (Lines 11-18)

```python
def analyze_file(path: str):
    stats = new_stats()  # Create empty statistics dictionary from analysis_core
    with open(path, "r", encoding="utf-8") as handle:  # Open log file in read mode
        for line in handle:  # Iterate through each line
            record = parse_log_line(line)  # Parse the log line into structured data
            if not record:  # Skip if line doesn't match log format
                continue
            update_stats(stats, record)  # Accumulate the parsed record into stats
    return stats  # Return the complete stats dictionary for this worker
```

**Purpose**: Each worker process calls this to analyze its assigned log file.

---

### Function: `ensure_world_size()` (Lines 21-28)

```python
def ensure_world_size(logs, world_size):
    expected = len(logs)  # Calculate expected rank count = number of logs + 1 (head)
    if world_size - 1 != expected:  # Check if actual MPI processes match expected
        hint = f"mpiexec -n {expected + 1} python parallel_analyzer.py --logs ..."  # Helpful hint
        raise SystemExit(  # Stop execution with error message
            f"Expected {expected + 1} ranks (1 head + {expected} workers) but got {world_size}. "
            f"Run: {hint}"
        )
```

**Purpose**: Validates that the number of MPI processes matches the number of logs (rank 0 is head, ranks 1..N are workers).

---

### Function: `build_plot()` (Lines 31-47)

```python
def build_plot(server_summaries: dict, output_path: Path):
    import matplotlib.pyplot as plt  # Import matplotlib dynamically

    names = list(server_summaries.keys())  # Get server names: ['server1', 'server2', 'server3']
    requests = [server_summaries[name]["total_requests"] for name in names]  # Extract request counts
    error_rates = [server_summaries[name]["error_rate"] * 100 for name in names]  # Extract error % per server

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))  # Create figure with 2 side-by-side subplots

    axes[0].bar(names, requests, color="#4f81bd")  # Left plot: bar chart of requests per server
    axes[0].set_title("Requests per server")  # Set title
    axes[0].set_ylabel("Requests")  # Set Y-axis label

    axes[1].bar(names, error_rates, color="#c0504d")  # Right plot: bar chart of error rates
    axes[1].set_title("Error rate (%)")  # Set title
    axes[1].set_ylabel("Percent")  # Set Y-axis label

    fig.tight_layout()  # Adjust spacing between subplots
    output_path.parent.mkdir(parents=True, exist_ok=True)  # Create output directory if needed
    fig.savefig(output_path, dpi=150)  # Save as PNG file
    plt.close(fig)  # Free memory
```

**Purpose**: Creates a static 2-subplot visualization showing requests and error rates per server.

---

### Function: `derive_rankings()` (Lines 50-67)

```python
def derive_rankings(server_summaries: dict):
    busiest = None  # Will store (server_name, total_requests) for busiest server
    highest_error = None  # Will store (server_name, error_rate) for highest error server

    for name, summary in server_summaries.items():  # Iterate through each server's summary
        total = summary["total_requests"]  # Get request count
        error_rate = summary["error_rate"]  # Get error rate (0.0 to 1.0)

        if total and (busiest is None or total > busiest[1]):  # If first server or this one has more requests
            busiest = (name, total)  # Update busiest

        if total and (highest_error is None or error_rate > highest_error[1]):  # If first server or this one has higher error rate
            highest_error = (name, error_rate)  # Update highest_error

    return {
        "busiest_server": busiest[0] if busiest else None,  # Return server name or None
        "highest_error_server": highest_error[0] if highest_error else None,  # Return server name or None
    }
```

**Purpose**: Determines which server had the most requests and which had the highest error rate.

---

### Function: `parse_args()` (Lines 70-75)

```python
def parse_args():
    parser = argparse.ArgumentParser(description="Parallel MPI log analyzer (head + workers per server log)")
    parser.add_argument("--logs", nargs="+", required=True, help="Paths to server log files...")
    # nargs="+" means 1 or more log file paths required
    
    parser.add_argument("--output", default="reports/parallel_summary.json", help="Where to write merged JSON...")
    # Default output location if not specified
    
    parser.add_argument("--plot", help="Optional path to write a summary plot (PNG).")
    # Optional plot path
    
    return parser.parse_args()  # Parse and return arguments from command line
```

**Purpose**: Parses command-line arguments for the script.

---

### Function: `main()` (Lines 78-130)

```python
def main():
    args = parse_args()  # Get parsed command-line arguments
    comm = MPI.COMM_WORLD  # Get MPI communicator (connects all processes)
    rank = comm.Get_rank()  # Get this process's rank (0=head, 1..N=workers)
    world_size = comm.Get_size()  # Get total number of processes

    if rank == 0:  # HEAD PROCESS
        ensure_world_size(args.logs, world_size)  # Validate process count matches log count
        
        gathered = comm.gather(None, root=0)  # Receive stats from all workers
        # gathered = [None (from head), stats1, stats2, stats3] for 3 logs
        
        merged_stats = new_stats()  # Create empty stats to merge into
        server_summaries = {}  # Dictionary to store per-server summaries
        
        for path, worker_stats in zip(args.logs, gathered[1:]):  # Iterate: log_path, stats pairs
            # gathered[1:] skips the None at index 0 (the head's contribution)
            
            merge_stats(merged_stats, worker_stats)  # Accumulate worker stats into global stats
            
            server_name = Path(path).stem  # Extract filename without extension ("server1" from "logs/server1.log")
            server_summaries[server_name] = summarize_stats(worker_stats)  # Create summary for this server

        global_summary = summarize_stats(merged_stats)  # Create global summary from merged stats
        rankings = derive_rankings(server_summaries)  # Find busiest and highest-error servers
        
        payload = {  # Create final JSON payload
            "servers": server_summaries,  # Per-server stats
            "global": global_summary,    # Merged/aggregated stats
            "rankings": rankings         # Which server is busiest/highest-error
        }

        output_path = Path(args.output)  # Get output file path
        output_path.parent.mkdir(parents=True, exist_ok=True)  # Create directory if needed
        with open(output_path, "w", encoding="utf-8") as handle:  # Open file for writing
            json.dump(payload, handle, indent=2)  # Write JSON with nice formatting

        if args.plot:  # If user specified --plot argument
            build_plot(server_summaries, Path(args.plot))  # Generate static visualization

        print("Parallel analysis complete:")  # Success message
        print(f"- JSON summary: {output_path}")
        if args.plot:
            print(f"- Plot: {Path(args.plot)}")
        return  # Exit after head completes

    # WORKER PROCESS CODE (rank >= 1)
    log_index = rank - 1  # Convert rank to log index (rank 1 → index 0, rank 2 → index 1)
    log_path = args.logs[log_index]  # Get this worker's log file path
    
    if not os.path.exists(log_path):  # Verify log file exists
        raise SystemExit(f"Log file not found: {log_path}")

    stats = analyze_file(log_path)  # Process the log file and compute stats
    comm.gather(stats, root=0)  # Send stats back to head (rank 0)


if __name__ == "__main__":
    main()  # Run the main function
```

**Purpose**: The main orchestration logic that:
- Head: waits for all workers, gathers stats, merges, writes JSON
- Workers: each processes its assigned log file and sends stats to head

---

---

## 2. GENERATE_LOGS.PY

This script creates realistic, imbalanced synthetic access logs with server-specific traffic patterns.

### Server Profiles (Lines 7-95)

```python
SERVER_PROFILES = [  # List of 3 realistic server configurations
    {
        "name": "server1",  # First server
        "region_weights": [  # IP distribution: where traffic comes from
            ((1, 49), 0.55),     # 55% from North America (IPs 1.x-49.x)
            ((50, 99), 0.20),    # 20% from Europe
            ((100, 149), 0.15),  # 15% from Asia
            ((150, 199), 0.05),  # 5% from Africa
            ((200, 254), 0.05),  # 5% from Other
        ],
        "peak_hours": list(range(9, 18)),  # Peak traffic 9 AM - 5 PM UTC (US business hours)
        "paths": [  # API endpoints and their popularity
            ("/api/v1/users", 0.18),      # 18% of requests
            ("/api/v1/orders", 0.15),
            # ... more endpoints with their traffic share
            ("/static/style.css", 0.02),
        ],
        "methods": [("GET", 0.65), ("POST", 0.22), ("PUT", 0.08), ("DELETE", 0.05)],
        # HTTP methods: 65% GET, 22% POST, etc.
        
        "statuses": [(200, 0.82), (201, 0.06), (400, 0.04), ...],
        # Status codes: 82% success (200), 6% created (201), 4% bad request, etc.
        
        "rows_multiplier": 1.2,  # Generate 120% of base rows (heavy traffic)
    },
    {
        "name": "server2",  # EU e-commerce server
        "region_weights": [
            ((1, 49), 0.15),      # Less North America traffic
            ((50, 99), 0.45),     # 45% from Europe (primary)
            ((100, 149), 0.30),   # Significant Asia traffic
            ((150, 199), 0.05),
            ((200, 254), 0.05),
        ],
        "peak_hours": list(range(10, 21)),  # Peak 10 AM - 8 PM UTC
        "paths": [  # E-commerce paths
            ("/products", 0.20),
            ("/cart", 0.12),
            ("/checkout", 0.06),
        ],
        "methods": [("GET", 0.72), ("POST", 0.20), ("PUT", 0.05), ("DELETE", 0.03)],
        "statuses": [...],
        "rows_multiplier": 1.0,  # Normal traffic volume
    },
    {
        "name": "server3",  # Asia admin/reporting server
        "region_weights": [
            ((1, 49), 0.08),      # Minimal North America
            ((50, 99), 0.12),
            ((100, 149), 0.55),   # 55% from Asia (primary)
            ((150, 199), 0.10),
            ((200, 254), 0.15),
        ],
        "peak_hours": list(range(0, 9)),  # Peak midnight-9 AM UTC (Asia business hours)
        "paths": [
            ("/admin/dashboard", 0.15),
            ("/reports/daily", 0.10),
        ],
        "methods": [("GET", 0.58), ("POST", 0.28), ("PUT", 0.08), ("DELETE", 0.06)],
        # More POST/PUT for admin operations
        
        "statuses": [...],
        "rows_multiplier": 0.7,  # Lower traffic (30% less)
    },
]
```

**Purpose**: Defines realistic traffic patterns for 3 different servers simulating real-world scenarios.

---

### Function: `weighted_choice()` (Lines 98-105)

```python
def weighted_choice(options):
    r = random.random()  # Generate random number 0.0-1.0
    cumulative = 0.0  # Start accumulating weights
    
    for value, weight in options:  # Iterate through (value, probability) pairs
        cumulative += weight  # Add this weight to running total
        if r <= cumulative:  # If random number falls in this range
            return value  # Return this value (weighted probability)
    
    return options[-1][0]  # Fallback: return last option if not returned above
```

**Purpose**: Selects a random item from a weighted list (e.g., 65% GET, 22% POST returns GET more often).

---

### Function: `random_ip_from_region_weights()` (Lines 108-115)

```python
def random_ip_from_region_weights(region_weights):
    """Pick IP range based on region weights, then generate IP."""
    ip_range = weighted_choice(region_weights)  # Pick region (e.g., (1, 49) for North America)
    first = random.randint(ip_range[0], ip_range[1])  # Random first octet in region range
    rest = [random.randint(0, 255) for _ in range(3)]  # Random 2nd, 3rd, 4th octets
    return f"{first}.{rest[0]}.{rest[1]}.{rest[2]}"  # Return formatted IP like "34.192.45.128"
```

**Purpose**: Generates a realistic IP address from the selected region.

---

### Function: `random_bytes()` (Lines 118-126)

```python
def random_bytes(status):
    if status >= 500:  # Server errors
        return random.randint(200, 1200)  # Small response (error page)
    
    if status >= 400:  # Client errors (400, 401, 403, 404)
        return random.randint(400, 2000)  # Slightly larger error response
    
    if status == 302:  # Redirect response
        return random.randint(100, 400)  # Minimal data sent
    
    return random.randint(800, 8000)  # Success responses: full data (8KB typical)
```

**Purpose**: Generates realistic response sizes based on status code.

---

### Function: `pick_hour()` (Lines 129-135)

```python
def pick_hour(peak_hours, span_hours):
    """70% chance to pick a peak hour, 30% any hour."""
    if random.random() < 0.70 and peak_hours:  # 70% of the time
        return random.choice(peak_hours)  # Return a peak hour (e.g., 9-17 for server1)
    
    return random.randint(0, min(23, span_hours - 1))  # 30% of the time: random hour
```

**Purpose**: Creates realistic traffic distribution (most traffic during peak hours, some off-peak).

---

### Function: `generate_line()` (Lines 138-151)

```python
def generate_line(profile, base_time, span_hours):
    hour = pick_hour(profile.get("peak_hours", []), span_hours)  # Get hour (peak or random)
    minute = random.randint(0, 59)  # Random minute
    second = random.randint(0, 59)  # Random second
    dt = base_time.replace(hour=hour % 24, minute=minute, second=second)  # Build timestamp
    
    ip = random_ip_from_region_weights(profile["region_weights"])  # Generate source IP
    method = weighted_choice(profile["methods"])  # Pick HTTP method (GET/POST/etc)
    path = weighted_choice(profile["paths"])  # Pick URL path
    status = weighted_choice(profile["statuses"])  # Pick response status
    size = random_bytes(status)  # Determine response size based on status
    
    timestamp = dt.strftime("%d/%b/%Y:%H:%M:%S %z")  # Format: "15/Mar/2025:14:32:01 +0000"
    return f"{ip} - - [{timestamp}] \"{method} {path} HTTP/1.1\" {status} {size}\n"
    # Returns: "192.168.1.45 - - [15/Mar/2025:14:32:01 +0000] "GET /api/users HTTP/1.1" 200 1234\n"
```

**Purpose**: Generates a single realistic log line based on server profile.

---

### Function: `write_log()` (Lines 154-162)

```python
def write_log(profile, base_rows, output_dir, span_hours):
    rows = int(base_rows * profile.get("rows_multiplier", 1.0))  # Scale rows by server multiplier
    # If base_rows=5000 and multiplier=1.2, generate 6000 lines
    
    base_time = datetime.now(timezone.utc).replace(microsecond=0)  # Current UTC time
    filename = Path(output_dir) / f"{profile['name']}.log"  # Create filepath like "logs/server1.log"
    
    with open(filename, "w", encoding="utf-8") as handle:  # Open file for writing
        for _ in range(rows):  # Generate requested number of lines
            handle.write(generate_line(profile, base_time, span_hours))  # Write one log line
    
    return filename, rows  # Return (filepath, line_count)
```

**Purpose**: Generates all log lines for one server and writes to file.

---

### Function: `parse_args()` (Lines 165-172)

```python
def parse_args():
    parser = argparse.ArgumentParser(description="Generate realistic imbalanced multi-server web access logs.")
    parser.add_argument("--servers", type=int, default=3, help="Number of servers (max 3)")
    parser.add_argument("--rows", type=int, default=5000, help="Base rows per server")
    parser.add_argument("--output-dir", default="logs", help="Output directory")
    parser.add_argument("--span-hours", type=int, default=24, help="Time window")
    parser.add_argument("--seed", type=int, help="RNG seed for reproducibility")
    return parser.parse_args()
```

**Purpose**: Parses command-line arguments.

---

### Function: `main()` (Lines 175-193)

```python
def main():
    args = parse_args()  # Parse arguments
    
    if args.seed is not None:  # If user specified --seed
        random.seed(args.seed)  # Set random seed for reproducible output
    
    available = len(SERVER_PROFILES)  # Count available profiles (3)
    if args.servers > available:  # Can't request more profiles than available
        raise SystemExit(f"--servers must be <= {available} (got {args.servers})")
    
    os.makedirs(args.output_dir, exist_ok=True)  # Create output directory if needed
    
    generated = []  # Track generated files
    
    for profile in SERVER_PROFILES[:args.servers]:  # Iterate through requested servers
        path, rows = write_log(profile, args.rows, args.output_dir, args.span_hours)  # Generate log
        generated.append((path, rows))  # Track result
    
    print(f"Generated {len(generated)} log files in {Path(args.output_dir).resolve()}")
    for path, rows in generated:
        print(f"  - {path.name}: {rows} lines")


if __name__ == "__main__":
    main()  # Run main
```

**Purpose**: Main entry point that generates all requested log files.

---

---

## 3. ANALYSIS_CORE.PY

Shared utility functions for parsing logs and accumulating statistics.

### Regular Expression Pattern (Lines 6-9)

```python
LOG_PATTERN = re.compile(
    r"(?P<ip>\d+\.\d+\.\d+\.\d+)\s+-\s+-\s+\[(?P<time>[^\]]+)\]\s+\"(?P<method>[A-Z]+)\s+(?P<path>[^\s]+)\s+HTTP/1\.1\"\s+(?P<status>\d{3})\s+(?P<size>\d+)",
)
```

**Breakdown**:
- `(?P<ip>\d+\.\d+\.\d+\.\d+)` – Named group "ip": matches 4 octets separated by dots (e.g., "192.168.1.1")
- `\s+-\s+-\s+` – Matches literal " - - " (spaces around dashes)
- `\[(?P<time>[^\]]+)\]` – Named group "time": anything inside brackets (timestamp)
- `\"(?P<method>[A-Z]+)` – Named group "method": uppercase letters after quote (GET, POST)
- `(?P<path>[^\s]+)` – Named group "path": non-whitespace characters (URL path)
- `HTTP/1\.1\" ` – Literal "HTTP/1.1\" followed by space
- `(?P<status>\d{3})` – Named group "status": exactly 3 digits (status code)
- `(?P<size>\d+)` – Named group "size": one or more digits (response bytes)

---

### Function: `ip_to_region()` (Lines 13-27)

```python
def ip_to_region(ip: str) -> str:
    """Synthetic IP-to-region mapping based on first octet."""
    try:
        first_octet = int(ip.split(".")[0])  # Extract first part of IP, convert to int
    except (ValueError, IndexError):
        return "Other"  # Return "Other" if parsing fails

    if 1 <= first_octet <= 49:  # IPs starting with 1-49
        return "North America"
    if 50 <= first_octet <= 99:  # IPs starting with 50-99
        return "Europe"
    if 100 <= first_octet <= 149:  # IPs starting with 100-149
        return "Asia"
    if 150 <= first_octet <= 199:  # IPs starting with 150-199
        return "Africa"
    return "Other"  # Everything else
```

**Purpose**: Maps IP addresses to regions based on first octet (deterministic geographic classification).

---

### Function: `parse_log_line()` (Lines 30-45)

```python
def parse_log_line(line: str) -> Dict[str, Any] | None:
    match = LOG_PATTERN.match(line.strip())  # Try to match regex against log line
    if not match:  # If regex doesn't match
        return None  # Invalid line, skip it

    time_str = match.group("time")  # Extract timestamp string from regex match
    try:
        ts = datetime.strptime(time_str, "%d/%b/%Y:%H:%M:%S %z")
        # Parse: "15/Mar/2025:14:32:01 +0000" → datetime object
    except ValueError:  # If timestamp format is wrong
        return None  # Skip line

    return {
        "ip": match.group("ip"),           # e.g., "192.168.1.45"
        "dt": ts,                          # datetime object
        "method": match.group("method"),   # e.g., "GET"
        "path": match.group("path"),       # e.g., "/api/users"
        "status": int(match.group("status")),  # e.g., 200
        "size": int(match.group("size")),      # e.g., 1234
    }
```

**Purpose**: Parses a single log line into a structured dictionary, or returns None if invalid.

---

### Function: `new_stats()` (Lines 48-58)

```python
def new_stats() -> Dict[str, Any]:
    return {
        "requests": 0,           # Count of all requests
        "bytes": 0,              # Total bytes transferred
        "status": Counter(),     # Tallies: {200: 523, 404: 12, 500: 3}
        "paths": Counter(),      # Tallies: {"/api/users": 150, "/api/orders": 120}
        "methods": Counter(),    # Tallies: {"GET": 650, "POST": 220}
        "regions": Counter(),    # Tallies: {"North America": 550, "Europe": 200}
        "hours": Counter(),      # Tallies: {9: 150, 10: 160, 11: 145} (traffic per hour)
        "errors": 0,             # Count of 4xx and 5xx responses
    }
```

**Purpose**: Creates an empty statistics container for accumulating metrics.

---

### Function: `update_stats()` (Lines 61-72)

```python
def update_stats(stats: Dict[str, Any], record: Dict[str, Any]) -> None:
    stats["requests"] += 1  # Increment request count
    stats["bytes"] += record["size"]  # Add response bytes to total
    stats["status"][record["status"]] += 1  # Tally this status code (200, 404, etc)
    stats["paths"][record["path"]] += 1  # Tally this URL path
    stats["methods"][record["method"]] += 1  # Tally this method (GET, POST)

    region = ip_to_region(record["ip"])  # Convert IP to region
    stats["regions"][region] += 1  # Tally requests from this region

    hour = record["dt"].hour  # Extract hour from timestamp (0-23)
    stats["hours"][hour] += 1  # Tally requests in this hour

    if record["status"] >= 400:  # If 4xx or 5xx response
        stats["errors"] += 1  # Count as error
```

**Purpose**: Updates statistics by processing a single parsed log record.

---

### Function: `merge_stats()` (Lines 75-85)

```python
def merge_stats(target: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    target["requests"] += incoming["requests"]  # Add request counts
    target["bytes"] += incoming["bytes"]  # Add byte totals
    target["errors"] += incoming["errors"]  # Add error counts

    for key in ("status", "paths", "methods", "regions", "hours"):  # For each Counter field
        target[key].update(incoming[key])  # Merge: adds counts from incoming to target

    return target
```

**Purpose**: Merges statistics from multiple workers (or any two stats dicts) into a combined result.

---

### Function: `summarize_stats()` (Lines 88-107)

```python
def summarize_stats(stats: Dict[str, Any], top_k: int = 5) -> Dict[str, Any]:
    total = stats["requests"]  # Total request count
    error_rate = stats["errors"] / total if total else 0.0  # Calculate: errors / total (or 0 if no requests)

    peak_hour = None  # Default: no peak hour
    if stats["hours"]:  # If there are any hourly tallies
        peak_hour = stats["hours"].most_common(1)[0][0]
        # most_common(1) returns [(hour, count), ...] → take [0] → (hour, count) → [0] → hour

    return {
        "total_requests": total,  # Total count
        "total_bytes": stats["bytes"],  # Total bytes
        "error_rate": error_rate,  # Error percentage (0.0 to 1.0)
        "status_breakdown": dict(stats["status"]),  # Convert Counter to dict: {200: 523, 404: 12}
        "method_breakdown": dict(stats["methods"]),  # {GET: 650, POST: 220}
        "region_distribution": dict(stats["regions"]),  # {North America: 550, Europe: 200}
        "hour_histogram": dict(stats["hours"]),  # {9: 150, 10: 160, ...}
        "peak_hour": peak_hour,  # Which hour had most traffic
        "top_paths": [  # Top 5 (top_k) paths
            {"path": path, "count": count}  # List of {path, count} dicts
            for path, count in stats["paths"].most_common(top_k)
        ],
    }
```

**Purpose**: Converts accumulated Counter objects into a JSON-serializable summary report.

---

---

## 4. DASHBOARD.PY

A Flask web application with an interactive Chart.js dashboard. This is a very large file, so I'll explain the key sections.

### Imports (Lines 1-11)

```python
import argparse        # Parse CLI args
import json            # JSON handling
import time            # Timing functions
import threading       # Background tasks (unused here but available)
from pathlib import Path  # File paths
from typing import Optional, List, Generator  # Type hints
from datetime import datetime  # Datetime handling

from flask import Flask, jsonify, send_file, abort, request, Response, stream_with_context
# Flask web framework: Flask (app), jsonify (return JSON), send_file (serve files),
# abort (HTTP errors), request (HTTP request info), Response/stream_with_context (streaming)

from render_template_string  # Render HTML template as string

from analysis_core import parse_log_line, ip_to_region, new_stats, update_stats, summarize_stats, merge_stats
# Reuse analysis utilities
```

---

### HTML_TEMPLATE (Lines 18-1000+)

This is a large HTML/CSS/JavaScript document embedded as a Python string. Key sections:

#### CSS Variables (Light/Dark Theme)
```css
:root {
  --bg: #f8fafc;           /* Light mode: light gray background */
  --bg2: #ffffff;          /* Light mode: white cards */
  --text: #1e293b;         /* Light mode: dark text */
  --accent: #3b82f6;       /* Blue primary color */
  --success: #22c55e;      /* Green for success */
  --warning: #f59e0b;      /* Amber for warnings */
}
.dark {
  --bg: #0f172a;           /* Dark mode: very dark background */
  --bg2: #1e293b;          /* Dark mode: dark gray cards */
  --text: #f1f5f9;         /* Dark mode: light text */
  /* ... dark versions of colors ... */
}
```

#### HTML Structure
- **Sidebar**: Fixed left panel with navigation items and theme toggle
- **Main**: Scrollable content area with 7 pages (Overview, Servers, Traffic, Geography, Errors, Paths, Logs)
- **Navigation**: Click nav items to show/hide views
- **Charts**: Canvas elements for Chart.js to render

#### JavaScript State Variables (Lines 470-474)
```javascript
let summaryData = null;      // Holds parsed JSON from /api/summary
let metaData = null;         // Holds server/region list from /api/meta
let charts = {};             // Dictionary of active Chart.js instances
let darkMode = localStorage.getItem('darkMode') === 'true';  // Remember theme preference
```

---

### Function: `applyTheme()` (Lines 477-483)

```javascript
function applyTheme() {
  document.body.classList.toggle('dark', darkMode);
  // Toggles 'dark' class on body, triggering CSS variable overrides
  
  document.getElementById('themeLabel').textContent = darkMode ? 'Light Mode' : 'Dark Mode';
  // Changes button text
  
  Object.values(charts).forEach(c => c && c.update && c.update());
  // Refreshes all charts with new colors
}
```

---

### API Fetch Functions (Lines 486-504)

```javascript
async function fetchJSON(url) {
  const res = await fetch(url);  // Make HTTP GET request
  if (!res.ok) throw new Error(`Failed: ${url}`);  // Throw if 404 or 500
  return res.json();  // Parse and return JSON
}

async function loadSummary() { return fetchJSON('/api/summary'); }
async function loadMeta() { return fetchJSON('/api/meta'); }
async function loadTimeseries(servers) {
  const params = servers && servers.length ? `?servers=${servers.join(',')}` : '';
  // Build URL like: "/api/timeseries?servers=server1,server2"
  return fetchJSON(`/api/timeseries${params}`);
}

async function loadRaw(opts) {
  const url = new URL('/api/raw', location.origin);  // Build URL object
  if (opts.server) url.searchParams.set('server', opts.server);  // Add query params
  if (opts.status_class) url.searchParams.set('status_class', opts.status_class);
  // ... more params ...
  url.searchParams.set('limit', '200');  // Limit results to 200
  return fetchJSON(url);
}
```

---

### Utility Functions (Lines 507-523)

```javascript
function toSorted(obj) {
  // Convert Counter dict to sorted array of [key, value] pairs
  return Object.entries(obj || {}).sort((a,b) => a[0].localeCompare(b[0]));
}

function destroy(id) {
  // Destroy old Chart.js instance to avoid memory leaks
  if (charts[id]) { 
    charts[id].destroy(); 
    delete charts[id]; 
  }
}

const palette = ['#3b82f6','#ef4444','#22c55e','#f59e0b',...];
// Color palette for charts

function getChartColors(isDark) {
  // Return chart colors based on theme
  return {
    gridColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
    textColor: isDark ? '#94a3b8' : '#64748b',
  };
}

function chartDefaults() {
  // Standard Chart.js configuration
  const colors = getChartColors(darkMode);
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: colors.textColor } } },
    scales: {
      x: { grid: { color: colors.gridColor }, ... },
      y: { grid: { color: colors.gridColor }, ... }
    }
  };
}
```

---

### Function: `buildFilters()` (Lines 536-560)

```javascript
function buildFilters() {
  // Populate dropdown menus with available options
  
  const regions = ['All', ...(metaData?.regions || [])];
  // Start with 'All' option, then add from metaData
  
  const servers = metaData?.servers || Object.keys(summaryData.servers || {});
  // Get server names from metaData, or extract from summary
  
  // Update each dropdown HTML:
  document.getElementById('globalRegion').innerHTML = 
    regions.map(r => `<option value="${r}">${...}</option>`).join('');
  // Generate: <option value="North America">North America</option>
  // <option value="Europe">Europe</option> ...
  
  // Similar for other dropdowns: globalServer, serverPicker, etc.
}
```

---

### Function: `renderStatsGrid()` (Lines 563-572)

```javascript
function renderStatsGrid() {
  // Display KPI cards at top of overview
  const g = summaryData.global || {};  // Get global stats
  const rankings = summaryData.rankings || {};
  
  const html = `
    <div class="stat-card">
      <div class="label">Total Requests</div>
      <div class="value">${(g.total_requests || 0).toLocaleString()}</div>
    </div>
    // ... more cards for bytes, error rate, peak hour, busiest server ...
  `;
  
  document.getElementById('statsGrid').innerHTML = html;  // Insert into page
}
```

---

### Function: `renderOverviewCharts()` (Lines 575-615)

```javascript
function renderOverviewCharts() {
  // Render 4 charts on Overview page
  
  // 1. Get filter values
  const region = document.getElementById('globalRegion').value;
  const serverFilter = document.getElementById('globalServer').value;
  
  // 2. Extract data for charts
  let names = Object.keys(servers);
  if (serverFilter !== 'All') names = names.filter(n => n === serverFilter);
  
  const reqs = names.map(n => 
    region === 'All' 
      ? (servers[n].total_requests || 0)
      : ((servers[n].region_distribution || {})[region] || 0)
  );
  // Get request count per server, optionally filtered by region
  
  // 3. Destroy old chart instance
  const reqType = document.getElementById('reqChartType').value;
  destroy('requests');
  
  // 4. Create new chart
  charts.requests = new Chart(document.getElementById('requestsChart'), {
    type: reqType,  // 'bar', 'doughnut', or 'polarArea'
    data: {
      labels: names,
      datasets: [{
        label: 'Requests',
        data: reqs,
        backgroundColor: palette.slice(0, names.length),
        borderColor: palette.slice(0, names.length),
        borderWidth: 1
      }]
    },
    options: {
      ...chartDefaults(),
      plugins: { legend: { display: reqType !== 'bar' } }
    }
  });
  
  // Repeat for errors chart, hourly chart, methods chart ...
}
```

---

### Function: `renderServerView()` (Lines 680-732)

```javascript
function renderServerView() {
  // Render detailed server page when user picks from dropdown
  
  const name = document.getElementById('serverPicker').value;
  const data = summaryData.servers?.[name];  // Get selected server's data
  
  // Render stats cards for this server
  const html = `
    <div class="stat-card">
      <div class="label">Requests</div>
      <div class="value">${(data.total_requests || 0).toLocaleString()}</div>
    </div>
    // ... more cards ...
  `;
  document.getElementById('serverStats').innerHTML = html;
  
  // Create charts specific to this server:
  // - Status breakdown (bar chart)
  // - Methods breakdown (doughnut)
  // - Region distribution (polar area)
  // - Hourly traffic (line)
  // - Top paths (table)
}
```

---

### Real-time Updates via SSE (Lines 1070-1095)

```javascript
function setupRealtime() {
  if (typeof(EventSource) === 'undefined') return;  // Browser doesn't support SSE
  
  try {
    const es = new EventSource('/api/stream');
    // Opens persistent connection to /api/stream endpoint
    
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);  // Parse incoming JSON
        if (data.type === 'summary') {
          summaryData = data.payload;  // Update cached data
          renderStatsGrid();
          renderOverviewCharts();
          // Re-render views with new data
          
          document.getElementById('liveIndicator').style.display = 'flex';
          // Show "Live" indicator
        }
      } catch (err) {
        console.error('SSE parse error', err);
      }
    };
    
    es.onerror = () => {
      document.getElementById('liveIndicator').style.display = 'none';
      // Hide indicator when connection breaks
    };
  } catch (err) {
    console.log('SSE not available');
  }
}
```

---

### Initialization (Lines 1098-1115)

```javascript
(async () => {
  applyTheme();  // Apply saved theme preference
  
  try {
    [summaryData, metaData] = await Promise.all([
      loadSummary(),    // Fetch /api/summary
      loadMeta().catch(() => null)  // Fetch /api/meta (optional)
    ]);
    // Wait for both requests in parallel
    
    buildFilters();     // Populate dropdowns
    renderStatsGrid();  // Show KPI cards
    renderOverviewCharts();  // Show main charts
    wireNav();          // Enable sidebar navigation
    wireFilters();      // Enable chart filters
    setupRealtime();    // Start SSE connection
  } catch (err) {
    console.error(err);
    document.getElementById('statsGrid').innerHTML = 
      '<div class="stat-card"><div class="label">Error</div><div class="value">Failed to load</div></div>';
  }
})();
```

---

### Flask Backend Functions (Lines 1120+)

```python
def load_summary(summary_path: Path):
    if not summary_path.exists():
        abort(404, "Summary JSON not found")  # Return HTTP 404 if file missing
    with open(summary_path, "r", encoding="utf-8") as handle:
        return json.load(handle)  # Parse and return JSON


def create_app(summary_path: Path, plot_path: Optional[Path] = None, logs_dir: Optional[Path] = None):
    app = Flask(__name__)  # Create Flask app
    
    summary_cache = {"data": None, "mtime": 0}  # Cache summary with modification time
    
    def get_summary():
        # Load summary, update cache if file changed
        if summary_path.exists():
            mtime = summary_path.stat().st_mtime  # Get file modification time
            if summary_cache["data"] is None or mtime > summary_cache["mtime"]:
                summary_cache["data"] = load_summary(summary_path)
                summary_cache["mtime"] = mtime
        return summary_cache["data"]
    
    @app.get("/")
    def index():
        return render_template_string(HTML_TEMPLATE, summary_path=summary_path)
        # Render HTML template (browser gets full UI)
    
    @app.get("/api/summary")
    def summary():
        return jsonify(get_summary())  # Return JSON summary
    
    @app.get("/api/meta")
    def meta():
        summary = get_summary()
        servers = sorted(summary.get("servers", {}).keys())
        regions = available_regions(summary)
        return jsonify({"servers": servers, "regions": regions})  # Return available options
    
    @app.get("/api/timeseries")
    def timeseries():
        # Return hourly traffic data
        servers_param = request.args.get("servers")  # Get query param
        selected = set(servers_param.split(",")) if servers_param else None
        # ... build hourly timeseries data ...
        return jsonify({"hours": hours, "per_server": per_server, "global": global_series})
    
    @app.get("/api/raw")
    def raw_logs():
        # Return raw log entries with filtering
        if logs_dir is None:
            abort(400, "Raw log browsing disabled")
        
        server = request.args.get("server")
        if not server:
            abort(400, "server query param required")
        
        log_path = logs_dir / f"{server}.log"
        
        # Parse filter parameters
        status_class = request.args.get("status_class")
        method_filter = request.args.get("method")
        region_filter = request.args.get("region")
        path_sub = request.args.get("path_sub")
        
        results = []
        with open(log_path, "r", encoding="utf-8") as handle:
            for line in handle:
                record = parse_log_line(line)
                if not record:
                    continue
                
                region = ip_to_region(record["ip"])
                
                # Apply filters
                if status_class and not str(record["status"]).startswith(status_class):
                    continue
                if method_filter and record["method"] != method_filter:
                    continue
                if region_filter and region_filter != region:
                    continue
                if path_sub and path_sub not in record["path"]:
                    continue
                
                results.append({
                    "ip": record["ip"],
                    "time": record["dt"].isoformat(),
                    "method": record["method"],
                    "path": record["path"],
                    "status": record["status"],
                    "bytes": record["size"],
                    "region": region,
                })
                
                if len(results) >= 200:  # Limit to 200
                    break
        
        return jsonify({"items": results, "count": len(results)})
    
    @app.get("/api/stream")
    def stream():
        # Server-Sent Events endpoint for real-time updates
        def generate() -> Generator[str, None, None]:
            last_mtime = 0
            while True:
                if summary_path.exists():
                    mtime = summary_path.stat().st_mtime
                    if mtime > last_mtime:  # File changed
                        last_mtime = mtime
                        data = get_summary()
                        yield f"data: {json.dumps({'type': 'summary', 'payload': data})}\n\n"
                        # SSE format: "data: <JSON>\n\n"
                time.sleep(2)  # Check every 2 seconds
        
        return Response(stream_with_context(generate()), mimetype="text/event-stream")
    
    return app


def main():
    args = parse_args()  # Parse CLI arguments
    summary_path = Path(args.summary)
    plot_path = Path(args.plot) if args.plot else None
    logs_dir = Path(args.logs_dir) if args.logs_dir else None
    
    app = create_app(summary_path, plot_path, logs_dir)
    
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
    # Start Flask dev server
```

---

## Summary of Data Flow

```
User runs: mpiexec -n 4 python parallel_analyzer.py --logs server{1,2,3}.log
    ↓
Head (rank 0): Validates world size
Workers (rank 1-3): Each loads their log file
    ↓
Each worker:
  - Opens log file
  - Parses each line with regex
  - Updates local stats (requests, bytes, errors, regions, paths, methods, hours)
  - Sends stats to head
    ↓
Head receives all worker stats
  - Merges all worker stats into global stats
  - Creates per-server summaries
  - Calculates rankings (busiest, highest-error servers)
  - Writes JSON report
  - Optionally creates static plots
    ↓
User runs: python dashboard.py --summary reports/parallel_summary.json --logs-dir logs --port 8000
    ↓
Dashboard starts Flask web server on localhost:8000
    ↓
User opens http://127.0.0.1:8000 in browser
    ↓
Browser loads HTML_TEMPLATE (full UI with all pages)
JavaScript initializes:
  - Fetches /api/summary (JSON summary)
  - Fetches /api/meta (available servers/regions)
  - Renders 4 charts on Overview page
  - Sets up navigation (clickable sidebar items)
  - Opens SSE stream to /api/stream for real-time updates
    ↓
User interacts:
  - Clicks sidebar items to switch pages
  - Changes dropdowns to filter charts
  - Selects servers to view details
  - Browses raw logs with filters
  - Toggles light/dark theme
```

This completes the full end-to-end explanation of all four Python files!
