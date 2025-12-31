# Parallel Log Analyzer (Distributed Web Logs)

A clean restart of the project to model a distributed web infrastructure using MPI: each worker rank represents a web server with its own access log, and rank 0 aggregates insights and visuals.

## Architecture
- Roles: rank 0 = head/aggregator; ranks 1..N = per-server analyzers.
- Data flow: each worker loads its server log, computes local stats, sends a compact summary to the head; the head merges, ranks servers, and (optionally) plots.
- Logs: multiple files (e.g., `logs/server1.log`, `logs/server2.log`, `logs/server3.log`). Each has distinct traffic patterns, IP ranges, and error rates.
- Regions: synthetic IP-to-region mapping by first octet (North America, Europe, Asia, Africa, Other) to simulate global distribution.

## Quickstart
1) Create env and install deps (Windows PowerShell):
```
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```
2) Generate sample logs (3 servers, 3000 lines each):
```
python generate_logs.py --servers 3 --rows 3000 --output-dir logs
```
3) Parallel analysis (requires `mpiexec`, use N = servers + 1):
```
mpiexec -n 4 python parallel_analyzer.py --logs logs/server1.log logs/server2.log logs/server3.log --output reports/parallel_summary.json --plot plots/summary.png
```
4) Serial baseline:
```
python serial_analyzer.py --logs logs/server1.log logs/server2.log logs/server3.log --output reports/serial_summary.json
```

## Metrics
- Per server: total requests, total bytes, error rate, status/method breakdown, top paths, region distribution, hourly histogram, peak hour.
- Global (head): merged totals plus busiest server and highest-error server derived from summaries.

## Files
- `generate_logs.py`: multi-server synthetic log generator with server-specific traffic patterns and IP ranges.
- `parallel_analyzer.py`: MPI head/worker analyzer; writes JSON summary and optional plot.
- `serial_analyzer.py`: single-process analyzer for comparison.
- `analysis_core.py`: shared parsing, accumulation, and summarization utilities.
- `requirements.txt`: Python dependencies.

## Notes
- Log format matches common access logs: `IP - - [timestamp] "METHOD PATH HTTP/1.1" STATUS BYTES` with timestamps in UTC.
- Expected MPI world size = number of logs + 1 (head). Example above: 3 logs → `-n 4`.
