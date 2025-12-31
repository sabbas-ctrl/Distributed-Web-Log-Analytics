import re
from collections import Counter
from datetime import datetime
from typing import Dict, Any

LOG_PATTERN = re.compile(
    r"(?P<ip>\d+\.\d+\.\d+\.\d+)\s+-\s+-\s+\[(?P<time>[^\]]+)\]\s+\"(?P<method>[A-Z]+)\s+(?P<path>[^\s]+)\s+HTTP/1\.1\"\s+(?P<status>\d{3})\s+(?P<size>\d+)",
)


def ip_to_region(ip: str) -> str:
    """Synthetic IP-to-region mapping based on first octet."""
    try:
        first_octet = int(ip.split(".")[0])
    except (ValueError, IndexError):
        return "Other"

    if 1 <= first_octet <= 49:
        return "North America"
    if 50 <= first_octet <= 99:
        return "Europe"
    if 100 <= first_octet <= 149:
        return "Asia"
    if 150 <= first_octet <= 199:
        return "Africa"
    return "Other"


def parse_log_line(line: str) -> Dict[str, Any] | None:
    match = LOG_PATTERN.match(line.strip())
    if not match:
        return None

    time_str = match.group("time")
    try:
        ts = datetime.strptime(time_str, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None

    return {
        "ip": match.group("ip"),
        "dt": ts,
        "method": match.group("method"),
        "path": match.group("path"),
        "status": int(match.group("status")),
        "size": int(match.group("size")),
    }


def new_stats() -> Dict[str, Any]:
    return {
        "requests": 0,
        "bytes": 0,
        "status": Counter(),
        "paths": Counter(),
        "methods": Counter(),
        "regions": Counter(),
        "hours": Counter(),
        "errors": 0,
    }


def update_stats(stats: Dict[str, Any], record: Dict[str, Any]) -> None:
    stats["requests"] += 1
    stats["bytes"] += record["size"]
    stats["status"][record["status"]] += 1
    stats["paths"][record["path"]] += 1
    stats["methods"][record["method"]] += 1

    region = ip_to_region(record["ip"])
    stats["regions"][region] += 1

    hour = record["dt"].hour
    stats["hours"][hour] += 1

    if record["status"] >= 400:
        stats["errors"] += 1


def merge_stats(target: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    target["requests"] += incoming["requests"]
    target["bytes"] += incoming["bytes"]
    target["errors"] += incoming["errors"]

    for key in ("status", "paths", "methods", "regions", "hours"):
        target[key].update(incoming[key])

    return target


def summarize_stats(stats: Dict[str, Any], top_k: int = 5) -> Dict[str, Any]:
    total = stats["requests"]
    error_rate = stats["errors"] / total if total else 0.0

    peak_hour = None
    if stats["hours"]:
        peak_hour = stats["hours"].most_common(1)[0][0]

    return {
        "total_requests": total,
        "total_bytes": stats["bytes"],
        "error_rate": error_rate,
        "status_breakdown": dict(stats["status"]),
        "method_breakdown": dict(stats["methods"]),
        "region_distribution": dict(stats["regions"]),
        "hour_histogram": dict(stats["hours"]),
        "peak_hour": peak_hour,
        "top_paths": [
            {"path": path, "count": count}
            for path, count in stats["paths"].most_common(top_k)
        ],
    }
