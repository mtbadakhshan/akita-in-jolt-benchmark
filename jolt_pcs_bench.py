#!/usr/bin/env python3
"""Benchmark Akita and Dory using the unmodified a16z/jolt profile harness."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
REPOSITORY = "https://github.com/a16z/jolt"
SCALES = (20, 22, 24, 26, 28)
THREADS = (1, 8)
SCHEMES = ("akita", "dory")
COMMIT_SPAN = {"akita": "akita_main_commit_with_precommitted", "dory": "commit_witness"}
RUSTFLAGS = "-C target-cpu=native"


def command_output(*command: str, cwd: Path | None = None, env=None) -> str:
    return subprocess.check_output(command, cwd=cwd, env=env, text=True, stderr=subprocess.STDOUT).strip()


def git(source: Path, *args: str) -> str:
    return command_output("git", "-C", str(source), *args)


def verify_source(source: Path) -> str:
    remote = git(source, "remote", "get-url", "origin")
    if remote.rstrip("/") not in {REPOSITORY, f"{REPOSITORY}.git"}:
        raise SystemExit(f"expected origin {REPOSITORY}, got {remote}")
    commit = git(source, "rev-parse", "HEAD")
    if git(source, "status", "--porcelain"):
        raise SystemExit("the a16z/jolt source tree must be clean")
    if git(source, "branch", "--show-current"):
        raise SystemExit("source must be detached at the resolved main commit")
    return commit


def native_features() -> tuple[str, set[str]]:
    architecture = platform.machine().lower()
    cfg = command_output("rustc", "--print", "cfg", "-C", "target-cpu=native")
    features = set(re.findall(r'target_feature="([^"]+)"', cfg))
    required = "avx512f" if architecture == "x86_64" else "neon" if architecture in {"arm64", "aarch64"} else None
    if required is None:
        raise SystemExit(f"unsupported benchmark architecture: {architecture}")
    if required not in features:
        raise SystemExit(
            f"native {architecture} build does not expose required {required}; refusing to benchmark"
        )
    return required, features


def environment(threads: int) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "RAYON_NUM_THREADS": str(threads),
            "RUSTFLAGS": RUSTFLAGS,
            "RUST_LOG": "off",
            "NO_COLOR": "1",
        }
    )
    return env


def build(source: Path, scheme: str, env: dict[str, str]) -> Path:
    target = source / f"target/benchmark-{scheme}"
    features = "profiling,akita" if scheme == "akita" else "profiling"
    command = [
        "cargo",
        "build",
        "--release",
        "--locked",
        "-p",
        "jolt-prover",
        "--features",
        features,
        "--target-dir",
        str(target),
    ]
    subprocess.run(command, cwd=source, env=env, check=True)
    return target / "release/jolt-prover"


def affinity_command(command: list[str], threads: int) -> tuple[list[str], str | None]:
    if platform.system() != "Linux":
        return command, None
    allowed = sorted(os.sched_getaffinity(0))
    if len(allowed) < threads:
        raise SystemExit(f"only {len(allowed)} CPUs are available; cannot run {threads}-thread row")
    cpu_list = ",".join(map(str, allowed[:threads]))
    return ["taskset", "-c", cpu_list, *command], cpu_list


def parse_duration(value: str) -> float:
    match = re.fullmatch(r"([0-9.]+)(ns|µs|us|ms|s)", value)
    if not match:
        raise ValueError(f"unrecognized duration: {value}")
    amount = float(match.group(1))
    return amount * {"ns": 1e-9, "µs": 1e-6, "us": 1e-6, "ms": 1e-3, "s": 1}[match.group(2)]


def parse_commit_seconds(log: str, scheme: str) -> float:
    span = re.escape(COMMIT_SPAN[scheme])
    values = re.findall(rf"{span}[^\n]*?close[^\n]*?time\.busy=([0-9.]+(?:ns|µs|us|ms|s))", log)
    if not values:
        raise RuntimeError(f"missing close timing for {COMMIT_SPAN[scheme]}")
    return sum(parse_duration(value) for value in values)


def parse_peak_rss(log: str) -> int:
    match = re.search(r"Peak RSS ([0-9.]+) (B|KiB|MiB|GiB)", log)
    if not match:
        raise RuntimeError("missing upstream Peak RSS metric")
    scale = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}[match.group(2)]
    return round(float(match.group(1)) * scale)


def run_directories(source: Path) -> set[Path]:
    root = source / "benchmark-runs"
    return {path for path in root.glob("*") if path.is_dir() and not path.is_symlink()}


def provenance(source: Path, commit: str, command: str, cpu_list: str | None, required_isa: str, features: set[str]) -> dict:
    return {
        "utc": datetime.now(timezone.utc).isoformat(),
        "repository": REPOSITORY,
        "branch": "main",
        "jolt_commit": commit,
        "command": command,
        "rustc": command_output("rustc", "-Vv"),
        "rustflags": RUSTFLAGS,
        "architecture": platform.machine(),
        "os": platform.platform(),
        "cpu_model": command_output("bash", "-lc", "lscpu | awk -F: '/Model name/{gsub(/^ +/,\"\",$2); print $2}'")
        if platform.system() == "Linux"
        else command_output("sysctl", "-n", "machdep.cpu.brand_string"),
        "cpu_affinity": cpu_list,
        "required_isa": required_isa,
        "native_target_features": sorted(features),
        "memory_bytes": int(command_output("bash", "-lc", "awk '/MemTotal/{print $2*1024}' /proc/meminfo"))
        if platform.system() == "Linux"
        else int(command_output("sysctl", "-n", "hw.memsize")),
    }


def run_sample(
    source: Path,
    binary: Path,
    out: Path,
    commit: str,
    required_isa: str,
    features: set[str],
    scheme: str,
    scale: int,
    threads: int,
    sample: int,
) -> dict:
    command = [
        str(binary),
        "profile",
        "--name",
        "sha2-chain",
        "--scale",
        str(scale),
        "--format",
        "default",
        "--backend",
        "reference",
    ]
    command, cpu_list = affinity_command(command, threads)
    env = environment(threads)
    before = run_directories(source)
    completed = subprocess.run(command, cwd=source, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log = completed.stdout
    if completed.returncode:
        raise RuntimeError(f"benchmark failed ({completed.returncode}):\n{log[-4000:]}")
    created = run_directories(source) - before
    if len(created) != 1:
        raise RuntimeError(f"expected one upstream run directory, found {sorted(created)}")
    upstream_run = created.pop()
    with (upstream_run / "timings.csv").open(newline="") as stream:
        row = next(csv.DictReader(stream))

    cell = out / "raw" / f"{scheme}-2p{scale}-t{threads}" / f"sample-{sample}"
    cell.mkdir(parents=True, exist_ok=True)
    (cell / "run.log").write_text(log)
    shutil.copy2(upstream_run / "timings.csv", cell / "timings.csv")
    rendered = " ".join(
        [
            f"RUSTFLAGS='{RUSTFLAGS}'",
            f"RAYON_NUM_THREADS={threads}",
            *command,
        ]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "scheme": scheme,
        "guest": "sha2-chain",
        "cycles_log2": scale,
        "trace_length": int(row["trace_length"]),
        "threads": threads,
        "sample": sample,
        "warmup": sample == 0,
        "commit_seconds": parse_commit_seconds(log, scheme),
        "prove_seconds": float(row["prover_time_s"]),
        "verify_seconds": float(row["verifier_parallel_time_s"]),
        "verify_single_thread_seconds": float(row["verifier_single_thread_time_s"]),
        "verifier_threads": int(row["verifier_parallel_threads"]),
        "setup_seconds": float(row["setup_time_s"]),
        "proof_bytes": int(row["proof_size"]),
        "peak_rss_bytes": parse_peak_rss(log),
        "verified": True,
        "provenance": provenance(source, commit, rendered, cpu_list, required_isa, features),
    }


def load_records(root: Path) -> list[dict]:
    path = root / "records.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def write_records(root: Path, records: list[dict]) -> None:
    (root / "records.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records))


def aggregate(records: list[dict]) -> dict[tuple[str, int, int], dict]:
    grouped: dict[tuple[str, int, int], list[dict]] = {}
    for row in records:
        if not row["warmup"]:
            grouped.setdefault((row["scheme"], row["cycles_log2"], row["threads"]), []).append(row)
    keys = ("commit_seconds", "prove_seconds", "verify_seconds", "setup_seconds", "proof_bytes", "peak_rss_bytes")
    return {group: {key: statistics.median(row[key] for row in rows) for key in keys} for group, rows in grouped.items()}


def render_report(root: Path) -> None:
    records = load_records(root)
    data = aggregate(records)
    commands = sorted({row["provenance"]["command"] for row in records})

    def val(scheme: str, scale: int, threads: int, key: str, divisor=1.0) -> str:
        row = data.get((scheme, scale, threads))
        return "--" if row is None else f"{row[key] / divisor:.2f}"

    lines = [
        "# Akita in Jolt: comparison with Dory",
        "",
        f"Source: `{REPOSITORY}` main at `{records[0]['provenance']['jolt_commit'] if records else 'pending'}`.",
        "All measured proofs completed the upstream full-verification correctness gate.",
        f"Native compilation was required to expose `{records[0]['provenance']['required_isa'] if records else 'AVX-512/NEON'}`.",
        "",
        "| Cycles | Threads | Akita commit (s) | Dory commit (s) | Akita prove (s) | Dory prove (s) | Dory/Akita | Akita verify (ms) | Dory verify (ms) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scale in SCALES:
        for threads in THREADS:
            a, d = data.get(("akita", scale, threads)), data.get(("dory", scale, threads))
            ratio = "--" if not a or not d else f"{d['prove_seconds']/a['prove_seconds']:.2f}"
            lines.append(
                f"| $2^{{{scale}}}$ | {threads} | {val('akita', scale, threads, 'commit_seconds')} "
                f"| {val('dory', scale, threads, 'commit_seconds')} | {val('akita', scale, threads, 'prove_seconds')} "
                f"| {val('dory', scale, threads, 'prove_seconds')} | {ratio} "
                f"| {val('akita', scale, threads, 'verify_seconds', .001)} "
                f"| {val('dory', scale, threads, 'verify_seconds', .001)} |"
            )
    lines += [
        "",
        "| Cycles | Akita proof (KB) | Dory proof (KB) | Akita RSS 1t (GiB) | Akita RSS 8t (GiB) | Dory RSS 1t (GiB) | Dory RSS 8t (GiB) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scale in SCALES:
        lines.append(
            f"| $2^{{{scale}}}$ | {val('akita', scale, 1, 'proof_bytes', 1000)} "
            f"| {val('dory', scale, 1, 'proof_bytes', 1000)} "
            f"| {val('akita', scale, 1, 'peak_rss_bytes', 1024**3)} "
            f"| {val('akita', scale, 8, 'peak_rss_bytes', 1024**3)} "
            f"| {val('dory', scale, 1, 'peak_rss_bytes', 1024**3)} "
            f"| {val('dory', scale, 8, 'peak_rss_bytes', 1024**3)} |"
        )
    lines += ["", "## Exact measured commands", ""]
    lines.extend(f"```sh\n{command}\n```" for command in commands)
    (root / "report.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("matrix")
    run = sub.add_parser("run")
    run.add_argument("--source", required=True, type=Path)
    run.add_argument("--out", required=True, type=Path)
    run.add_argument("--scheme", choices=SCHEMES)
    run.add_argument("--scales", nargs="+", type=int, choices=SCALES, default=SCALES)
    run.add_argument("--threads", nargs="+", type=int, choices=THREADS, default=THREADS)
    run.add_argument("--samples", type=int, default=3)
    compare = sub.add_parser("compare")
    compare.add_argument("results", type=Path)
    args = parser.parse_args()
    if args.action == "matrix":
        for scheme in SCHEMES:
            for scale in SCALES:
                for threads in THREADS:
                    print(f"{scheme}\tsha2-chain\t2^{scale}\t{threads} threads")
        return
    if args.action == "compare":
        render_report(args.results.resolve())
        return
    source, out = args.source.resolve(), args.out.resolve()
    commit = verify_source(source)
    required_isa, features = native_features()
    out.mkdir(parents=True, exist_ok=True)
    records = load_records(out)
    schemes = (args.scheme,) if args.scheme else SCHEMES
    for scheme in schemes:
        binary = build(source, scheme, environment(max(args.threads)))
        for scale in args.scales:
            for threads in args.threads:
                for sample in range(args.samples + 1):
                    record = run_sample(
                        source, binary, out, commit, required_isa, features,
                        scheme, scale, threads, sample,
                    )
                    records.append(record)
                    write_records(out, records)
    render_report(out)


if __name__ == "__main__":
    main()
