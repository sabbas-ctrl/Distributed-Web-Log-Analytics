import argparse
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVER_PROFILES = [
    {
        "name": "server1",
        "ip_range": (12, 48),
        "paths": [
            ("/api", 0.25),
            ("/api/users", 0.2),
            ("/api/orders", 0.2),
            ("/api/search", 0.15),
            ("/health", 0.1),
            ("/static/app.js", 0.1),
        ],
        "methods": [("GET", 0.7), ("POST", 0.2), ("PUT", 0.05), ("DELETE", 0.05)],
        "statuses": [(200, 0.86), (201, 0.05), (400, 0.03), (404, 0.03), (500, 0.03)],
    },
    {
        "name": "server2",
        "ip_range": (64, 98),
        "paths": [
            ("/products", 0.35),
            ("/products/featured", 0.2),
            ("/cart", 0.15),
            ("/checkout", 0.1),
            ("/static/site.css", 0.1),
            ("/health", 0.1),
        ],
        "methods": [("GET", 0.8), ("POST", 0.15), ("PUT", 0.03), ("DELETE", 0.02)],
        "statuses": [(200, 0.88), (302, 0.04), (400, 0.02), (404, 0.03), (500, 0.03)],
    },
    {
        "name": "server3",
        "ip_range": (110, 148),
        "paths": [
            ("/admin", 0.25),
            ("/admin/login", 0.2),
            ("/reports", 0.2),
            ("/api", 0.15),
            ("/health", 0.1),
            ("/static/admin.js", 0.1),
        ],
        "methods": [("GET", 0.65), ("POST", 0.25), ("PUT", 0.05), ("DELETE", 0.05)],
        "statuses": [(200, 0.8), (201, 0.05), (401, 0.03), (403, 0.04), (500, 0.08)],
    },
]


def weighted_choice(options):
    r = random.random()
    cumulative = 0.0
    for value, weight in options:
        cumulative += weight
        if r <= cumulative:
            return value
    return options[-1][0]


def random_ip(ip_range):
    first = random.randint(ip_range[0], ip_range[1])
    rest = [random.randint(0, 255) for _ in range(3)]
    return f"{first}.{rest[0]}.{rest[1]}.{rest[2]}"


def random_bytes(status):
    if status >= 500:
        return random.randint(200, 900)
    if status >= 400:
        return random.randint(400, 1500)
    return random.randint(900, 6000)


def generate_line(profile, base_time, span_seconds):
    dt = base_time + timedelta(seconds=random.randint(0, span_seconds))
    ip = random_ip(profile["ip_range"])
    method = weighted_choice(profile["methods"])
    path = weighted_choice(profile["paths"])
    status = weighted_choice(profile["statuses"])
    size = random_bytes(status)
    timestamp = dt.strftime("%d/%b/%Y:%H:%M:%S %z")
    return f"{ip} - - [{timestamp}] \"{method} {path} HTTP/1.1\" {status} {size}\n"


def write_log(profile, rows, output_dir, span_hours):
    base_time = datetime.now(timezone.utc) - timedelta(hours=span_hours)
    span_seconds = span_hours * 3600
    filename = Path(output_dir) / f"{profile['name']}.log"
    with open(filename, "w", encoding="utf-8") as handle:
        for _ in range(rows):
            handle.write(generate_line(profile, base_time, span_seconds))
    return filename


def parse_args():
    parser = argparse.ArgumentParser(description="Generate synthetic multi-server web access logs.")
    parser.add_argument("--servers", type=int, default=3, help="Number of server logs to generate (max 3 by default).")
    parser.add_argument("--rows", type=int, default=3000, help="Number of rows per server log.")
    parser.add_argument("--output-dir", default="logs", help="Directory to place generated log files.")
    parser.add_argument("--span-hours", type=int, default=24, help="Time window to span for timestamps.")
    parser.add_argument("--seed", type=int, help="Optional RNG seed for reproducibility.")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    available = len(SERVER_PROFILES)
    if args.servers > available:
        raise SystemExit(f"--servers must be <= {available} (got {args.servers})")

    os.makedirs(args.output_dir, exist_ok=True)

    generated = []
    for profile in SERVER_PROFILES[: args.servers]:
        path = write_log(profile, args.rows, args.output_dir, args.span_hours)
        generated.append(path)

    print(f"Generated {len(generated)} log files in {Path(args.output_dir).resolve()}")
    for path in generated:
        print(f"- {path.name}")


if __name__ == "__main__":
    main()
