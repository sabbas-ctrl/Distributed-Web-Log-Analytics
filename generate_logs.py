import argparse
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Realistic imbalanced server profiles
# - server1: US-based API server, peak traffic 9-17 UTC, heavy North America
# - server2: EU e-commerce, peak 12-20 UTC, heavy Europe/Asia
# - server3: Asia-Pacific admin/reports, peak 0-8 UTC, heavy Asia/Other

SERVER_PROFILES = [
    {
        "name": "server1",
        "region_weights": [
            ((1, 49), 0.55),     # North America dominant
            ((50, 99), 0.20),    # Europe
            ((100, 149), 0.15),  # Asia
            ((150, 199), 0.05),  # Africa
            ((200, 254), 0.05),  # Other
        ],
        "peak_hours": list(range(9, 18)),  # 9-17 UTC
        "paths": [
            ("/api/v1/users", 0.18),
            ("/api/v1/orders", 0.15),
            ("/api/v1/products", 0.12),
            ("/api/v1/search", 0.10),
            ("/api/v1/auth/login", 0.08),
            ("/api/v1/auth/logout", 0.04),
            ("/api/v2/users", 0.08),
            ("/api/v2/orders", 0.07),
            ("/health", 0.08),
            ("/metrics", 0.05),
            ("/static/app.js", 0.03),
            ("/static/style.css", 0.02),
        ],
        "methods": [("GET", 0.65), ("POST", 0.22), ("PUT", 0.08), ("DELETE", 0.05)],
        "statuses": [(200, 0.82), (201, 0.06), (400, 0.04), (401, 0.02), (404, 0.03), (500, 0.02), (503, 0.01)],
        "rows_multiplier": 1.2,
    },
    {
        "name": "server2",
        "region_weights": [
            ((1, 49), 0.15),     # North America
            ((50, 99), 0.45),    # Europe dominant
            ((100, 149), 0.30),  # Asia secondary
            ((150, 199), 0.05),  # Africa
            ((200, 254), 0.05),  # Other
        ],
        "peak_hours": list(range(10, 21)),  # 10-20 UTC
        "paths": [
            ("/products", 0.20),
            ("/products/featured", 0.10),
            ("/products/category/electronics", 0.08),
            ("/products/category/clothing", 0.07),
            ("/cart", 0.12),
            ("/cart/add", 0.08),
            ("/checkout", 0.06),
            ("/checkout/payment", 0.05),
            ("/orders/history", 0.06),
            ("/account/profile", 0.05),
            ("/health", 0.05),
            ("/static/site.css", 0.04),
            ("/static/checkout.js", 0.04),
        ],
        "methods": [("GET", 0.72), ("POST", 0.20), ("PUT", 0.05), ("DELETE", 0.03)],
        "statuses": [(200, 0.85), (201, 0.04), (302, 0.03), (400, 0.02), (404, 0.03), (500, 0.02), (502, 0.01)],
        "rows_multiplier": 1.0,
    },
    {
        "name": "server3",
        "region_weights": [
            ((1, 49), 0.08),     # North America minimal
            ((50, 99), 0.12),    # Europe
            ((100, 149), 0.55),  # Asia dominant
            ((150, 199), 0.10),  # Africa
            ((200, 254), 0.15),  # Other significant
        ],
        "peak_hours": list(range(0, 9)),  # 0-8 UTC (Asia business hours)
        "paths": [
            ("/admin/dashboard", 0.15),
            ("/admin/users", 0.10),
            ("/admin/users/create", 0.05),
            ("/admin/settings", 0.08),
            ("/admin/login", 0.12),
            ("/reports/daily", 0.10),
            ("/reports/weekly", 0.08),
            ("/reports/monthly", 0.06),
            ("/reports/export", 0.05),
            ("/api/internal/sync", 0.08),
            ("/health", 0.05),
            ("/static/admin.js", 0.05),
            ("/static/reports.css", 0.03),
        ],
        "methods": [("GET", 0.58), ("POST", 0.28), ("PUT", 0.08), ("DELETE", 0.06)],
        "statuses": [(200, 0.75), (201, 0.06), (400, 0.04), (401, 0.04), (403, 0.05), (404, 0.02), (500, 0.03), (503, 0.01)],
        "rows_multiplier": 0.7,
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


def random_ip_from_region_weights(region_weights):
    """Pick IP range based on region weights, then generate IP."""
    ip_range = weighted_choice(region_weights)
    first = random.randint(ip_range[0], ip_range[1])
    rest = [random.randint(0, 255) for _ in range(3)]
    return f"{first}.{rest[0]}.{rest[1]}.{rest[2]}"


def random_bytes(status):
    if status >= 500:
        return random.randint(200, 1200)
    if status >= 400:
        return random.randint(400, 2000)
    if status == 302:
        return random.randint(100, 400)
    return random.randint(800, 8000)


def pick_hour(peak_hours, span_hours):
    """70% chance to pick a peak hour, 30% any hour."""
    if random.random() < 0.70 and peak_hours:
        return random.choice(peak_hours)
    return random.randint(0, min(23, span_hours - 1))


def generate_line(profile, base_time, span_hours):
    hour = pick_hour(profile.get("peak_hours", []), span_hours)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    dt = base_time.replace(hour=hour % 24, minute=minute, second=second)
    
    ip = random_ip_from_region_weights(profile["region_weights"])
    method = weighted_choice(profile["methods"])
    path = weighted_choice(profile["paths"])
    status = weighted_choice(profile["statuses"])
    size = random_bytes(status)
    timestamp = dt.strftime("%d/%b/%Y:%H:%M:%S %z")
    return f"{ip} - - [{timestamp}] \"{method} {path} HTTP/1.1\" {status} {size}\n"


def write_log(profile, base_rows, output_dir, span_hours):
    rows = int(base_rows * profile.get("rows_multiplier", 1.0))
    base_time = datetime.now(timezone.utc).replace(microsecond=0)
    filename = Path(output_dir) / f"{profile['name']}.log"
    with open(filename, "w", encoding="utf-8") as handle:
        for _ in range(rows):
            handle.write(generate_line(profile, base_time, span_hours))
    return filename, rows


def parse_args():
    parser = argparse.ArgumentParser(description="Generate realistic imbalanced multi-server web access logs.")
    parser.add_argument("--servers", type=int, default=3, help="Number of server logs to generate (max 3).")
    parser.add_argument("--rows", type=int, default=5000, help="Base rows per server (adjusted by profile multiplier).")
    parser.add_argument("--output-dir", default="logs", help="Directory for generated log files.")
    parser.add_argument("--span-hours", type=int, default=24, help="Time window for timestamps.")
    parser.add_argument("--seed", type=int, help="RNG seed for reproducibility.")
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
    for profile in SERVER_PROFILES[:args.servers]:
        path, rows = write_log(profile, args.rows, args.output_dir, args.span_hours)
        generated.append((path, rows))

    print(f"Generated {len(generated)} log files in {Path(args.output_dir).resolve()}")
    for path, rows in generated:
        print(f"  - {path.name}: {rows} lines")


if __name__ == "__main__":
    main()
