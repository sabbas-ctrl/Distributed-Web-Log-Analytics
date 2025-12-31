import argparse
import json
import os
from pathlib import Path

from mpi4py import MPI

from analysis_core import new_stats, parse_log_line, summarize_stats, update_stats, merge_stats


def analyze_file(path: str):
    stats = new_stats()
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            record = parse_log_line(line)
            if not record:
                continue
            update_stats(stats, record)
    return stats


def ensure_world_size(logs, world_size):
    expected = len(logs)
    if world_size - 1 != expected:
        hint = f"mpiexec -n {expected + 1} python parallel_analyzer.py --logs ..."
        raise SystemExit(
            f"Expected {expected + 1} ranks (1 head + {expected} workers) but got {world_size}. "
            f"Run: {hint}"
        )


def build_plot(server_summaries: dict, output_path: Path):
    import matplotlib.pyplot as plt

    names = list(server_summaries.keys())
    requests = [server_summaries[name]["total_requests"] for name in names]
    error_rates = [server_summaries[name]["error_rate"] * 100 for name in names]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    axes[0].bar(names, requests, color="#4f81bd")
    axes[0].set_title("Requests per server")
    axes[0].set_ylabel("Requests")

    axes[1].bar(names, error_rates, color="#c0504d")
    axes[1].set_title("Error rate (%)")
    axes[1].set_ylabel("Percent")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def derive_rankings(server_summaries: dict):
    busiest = None
    highest_error = None

    for name, summary in server_summaries.items():
        total = summary["total_requests"]
        error_rate = summary["error_rate"]

        if total and (busiest is None or total > busiest[1]):
            busiest = (name, total)

        if total and (highest_error is None or error_rate > highest_error[1]):
            highest_error = (name, error_rate)

    return {
        "busiest_server": busiest[0] if busiest else None,
        "highest_error_server": highest_error[0] if highest_error else None,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Parallel MPI log analyzer (head + workers per server log)")
    parser.add_argument("--logs", nargs="+", required=True, help="Paths to server log files (one per worker rank).")
    parser.add_argument("--output", default="reports/parallel_summary.json", help="Where to write merged JSON summary.")
    parser.add_argument("--plot", help="Optional path to write a summary plot (PNG).")
    return parser.parse_args()


def main():
    args = parse_args()
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    world_size = comm.Get_size()

    if rank == 0:
        ensure_world_size(args.logs, world_size)
        gathered = comm.gather(None, root=0)
        merged_stats = new_stats()
        server_summaries = {}
        for path, worker_stats in zip(args.logs, gathered[1:]):
            merge_stats(merged_stats, worker_stats)
            server_name = Path(path).stem
            server_summaries[server_name] = summarize_stats(worker_stats)

        global_summary = summarize_stats(merged_stats)
        rankings = derive_rankings(server_summaries)
        payload = {"servers": server_summaries, "global": global_summary, "rankings": rankings}

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

        if args.plot:
            build_plot(server_summaries, Path(args.plot))

        print("Parallel analysis complete:")
        print(f"- JSON summary: {output_path}")
        if args.plot:
            print(f"- Plot: {Path(args.plot)}")
        return

    # Worker ranks
    log_index = rank - 1
    log_path = args.logs[log_index]
    if not os.path.exists(log_path):
        raise SystemExit(f"Log file not found: {log_path}")

    stats = analyze_file(log_path)
    comm.gather(stats, root=0)


if __name__ == "__main__":
    main()
