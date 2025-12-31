import argparse
import json
from pathlib import Path

from analysis_core import merge_stats, new_stats, parse_log_line, summarize_stats, update_stats


def analyze_file(path: str):
    stats = new_stats()
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            record = parse_log_line(line)
            if not record:
                continue
            update_stats(stats, record)
    return stats


def parse_args():
    parser = argparse.ArgumentParser(description="Single-process log analyzer for comparison")
    parser.add_argument("--logs", nargs="+", required=True, help="Paths to server log files.")
    parser.add_argument("--output", default="reports/serial_summary.json", help="Where to write merged JSON summary.")
    return parser.parse_args()


def main():
    args = parse_args()
    merged_stats = new_stats()

    for log in args.logs:
        stats = analyze_file(log)
        merge_stats(merged_stats, stats)

    summary = summarize_stats(merged_stats)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    print("Serial analysis complete:")
    print(f"- JSON summary: {output_path}")


if __name__ == "__main__":
    main()
