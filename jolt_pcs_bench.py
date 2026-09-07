#!/usr/bin/env python3
"""Run and report the pinned Jolt Akita-versus-Dory experiment."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
SCALES = (20, 22, 24, 26, 28)
THREADS = (1, 8)
SCHEMES = ("akita", "dory")
JOLT_COMMIT = "00610882ef303e8a6b5b0d055a62aad3b96574bd"
JOLT_SUBMODULE_COMMIT = "8ba924aff76eb812c6e1f75dcb96496bfa5c76f9"
COMMIT_SPANS = ("CommitmentScheme::commit_batch", "commit_witness")


def run_checked(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def verify_source(source: Path) -> None:
    manifest_path = source / ".benchmark-source.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        actual = manifest.get("jolt_commit")
        nested = manifest.get("jolt_submodule_commit")
    else:
        actual = git(source, "rev-parse", "HEAD")
        nested = git(source / "third-party/jolt", "rev-parse", "HEAD")
    if actual != JOLT_COMMIT or nested != JOLT_SUBMODULE_COMMIT:
        raise SystemExit(
            f"source pin mismatch: root={actual}, nested={nested}; "
            f"expected {JOLT_COMMIT}, {JOLT_SUBMODULE_COMMIT}"
        )
    dirty = "" if manifest_path.exists() else git(source, "status", "--porcelain")
    allowed = "examples-rs/prover-daemon/"
    unexpected = [line for line in dirty.splitlines() if allowed not in line]
    if unexpected:
        raise SystemExit("Jolt source has unrelated changes:\n" + "\n".join(unexpected))


def prepare_profile(source: Path, output: Path, scale: int) -> tuple[Path, Path]:
    base = source / "examples/sha2-chain-profile-29"
    profile = output / "profiles" / f"sha2-chain-{scale}"
    inputs = output / "inputs" / f"sha2-chain-{scale}"
    profile.mkdir(parents=True, exist_ok=True)
    inputs.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base / "program.elf", profile / "program.elf")
    metadata = json.loads((base / "program.json").read_text())
    metadata["max_trace_length"] = 1 << scale
    (profile / "program.json").write_text(json.dumps(metadata, indent=2) + "\n")
    run_checked(
        [
            "cargo",
            "run",
            "--release",
            "--manifest-path",
            "examples-rs/input-generator/Cargo.toml",
            "--",
            "--guest-type",
            "sha2-chain",
            "--trace-power",
            str(scale),
            "--output-dir",
            str(inputs),
        ],
        cwd=source,
    )
    return profile, inputs


def _trace_events(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    return payload if isinstance(payload, list) else payload.get("traceEvents", [])


def commitment_seconds(path: Path) -> float | None:
    """Sum complete commitment spans in a Chrome trace."""
    total_us = 0.0
    for event in _trace_events(path):
        if event.get("ph") == "X" and event.get("name") in COMMIT_SPANS:
            total_us += float(event.get("dur", 0.0))
    return total_us / 1_000_000 if total_us else None


def provenance(source: Path, command: str) -> dict:
    def output(*cmd: str) -> str:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()

    return {
        "utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "jolt_commit": JOLT_COMMIT,
        "jolt_submodule_commit": JOLT_SUBMODULE_COMMIT,
        "rustc": output("rustc", "-Vv"),
        "os": platform.platform(),
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count(),
        "cpu_model": output("bash", "-lc", "lscpu | awk -F: '/Model name/{gsub(/^ +/,\"\",$2); print $2}'"),
        "memory_bytes": int(output("bash", "-lc", "awk '/MemTotal/{print $2*1024}' /proc/meminfo")),
        "source_dirty": (
            ""
            if (source / ".benchmark-source.json").exists()
            else git(source, "status", "--porcelain")
        ),
    }


def response_value(response: dict, snake: str, camel: str):
    return response.get(snake, response.get(camel))


def collect_cell(
    source: Path,
    out_dir: Path,
    scheme: str,
    scale: int,
    threads: int,
    samples: int,
    skip_build: bool,
) -> list[dict]:
    cell = out_dir / "raw" / f"{scheme}-2p{scale}-t{threads}"
    logs = cell / "integration"
    traces = cell / "traces"
    profiles = cell / "profiling"
    for path in (logs, traces, profiles):
        path.mkdir(parents=True, exist_ok=True)
    elf, inputs = prepare_profile(source, out_dir, scale)
    pcs = f"{scheme}-pcs"
    command = [
        "bash",
        "scripts/test-integration.sh",
        "--pcs",
        pcs,
        "--backend",
        "rust-only",
        "--program-mode",
        "committed",
        "--trace-power",
        str(scale),
        "--elf-profile",
        str(elf),
        "--input-profile",
        str(inputs),
        "--num-runs",
        str(samples + 1),
    ]
    if skip_build:
        command.append("--skip-build")
    rendered = " ".join(
        [
            f"RAYON_NUM_THREADS={threads}",
            "JOLT_ALLOW_FEWER_RUNS=1",
            f"JOLT_INTEGRATION_LOG_DIR={logs}",
            f"JOLT_TRACE_DIR={traces}",
            f"JOLT_PROFILE_DIR={profiles}",
            *map(str, command),
        ]
    )
    (cell / "command.txt").write_text(rendered + "\n")
    env = os.environ.copy()
    bundled_protoc = Path(__file__).resolve().parent / ".tools/protoc/bin/protoc"
    if bundled_protoc.exists():
        env["PROTOC"] = str(bundled_protoc)
    bundled_grpcurl = Path(__file__).resolve().parent / ".tools/grpcurl"
    if bundled_grpcurl.exists():
        env["PATH"] = f"{bundled_grpcurl}:{env.get('PATH', '')}"
    env.update(
        {
            "RAYON_NUM_THREADS": str(threads),
            "JOLT_ALLOW_FEWER_RUNS": "1",
            "JOLT_INTEGRATION_LOG_DIR": str(logs),
            "JOLT_TRACE_DIR": str(traces),
            "JOLT_PROFILE_DIR": str(profiles),
            "JOLT_WRITE_SUMMARY": "0",
        }
    )
    with (cell / "run.log").open("w") as log:
        subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    prov = provenance(source, rendered)
    records = []
    for proof_id in range(2, samples + 2):
        response_path = logs / f"prover_run_{proof_id}_response.json"
        response = json.loads(response_path.read_text())
        trace_matches = list(traces.glob(f"rust-driver-proof-{proof_id}-pid-*.json"))
        if len(trace_matches) != 1:
            raise RuntimeError(f"expected one trace for proof {proof_id}, found {trace_matches}")
        record = {
            "schema_version": SCHEMA_VERSION,
            "status": "ok",
            "scheme": scheme,
            "guest": "sha2-chain",
            "cycles_log2": scale,
            "threads": threads,
            "sample": proof_id - 1,
            "verified": bool(response_value(response, "verified", "verified")),
            "proof_bytes": int(response_value(response, "proof_size_bytes", "proofSizeBytes")),
            "prove_seconds": float(response_value(response, "duration_secs", "durationSecs")),
            "verify_seconds": float(
                response_value(response, "verify_duration_secs", "verifyDurationSecs")
            ),
            "total_seconds": float(
                response_value(response, "total_duration_secs", "totalDurationSecs")
            ),
            "commit_seconds": commitment_seconds(trace_matches[0]),
            "peak_rss_bytes": int(response_value(response, "peak_rss_bytes", "peakRssBytes")),
            "provenance": prov,
        }
        if not record["verified"] or record["proof_bytes"] <= 0:
            raise RuntimeError(f"invalid proof result in {response_path}")
        if record["commit_seconds"] is None:
            raise RuntimeError(f"commitment span missing from {trace_matches[0]}")
        records.append(record)
    with (cell / "records.jsonl").open("w") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    return records


def load_records(root: Path) -> list[dict]:
    records = []
    for path in sorted((root / "raw").glob("*/records.jsonl")):
        records.extend(json.loads(line) for line in path.read_text().splitlines() if line)
    return records


def med(values) -> float:
    return statistics.median(values)


def aggregate(records: list[dict]) -> dict[tuple[str, int, int], dict]:
    grouped: dict[tuple[str, int, int], list[dict]] = {}
    for record in records:
        grouped.setdefault(
            (record["scheme"], record["cycles_log2"], record["threads"]), []
        ).append(record)
    return {
        key: {
            "commit": med(row["commit_seconds"] for row in rows),
            "prove": med(row["prove_seconds"] for row in rows),
            "verify_ms": 1000 * med(row["verify_seconds"] for row in rows),
            "proof_kb": med(row["proof_bytes"] for row in rows) / 1000,
            "rss_gib": med(row["peak_rss_bytes"] for row in rows) / (1024**3),
        }
        for key, rows in grouped.items()
    }


def render_report(root: Path) -> None:
    records = load_records(root)
    if not records:
        raise SystemExit(f"no records found under {root}")
    data = aggregate(records)
    commands = sorted({r["provenance"]["command"] for r in records})

    def value(scheme: str, scale: int, threads: int, key: str, digits: int = 2) -> str:
        row = data.get((scheme, scale, threads))
        return "--" if row is None else f"{row[key]:.{digits}f}"

    md = [
        "# Jolt with Akita and Dory",
        "",
        "The experiment uses the same `sha2-chain` ELF and deterministic input rule at each",
        "trace cap. Every measured serialized proof verified successfully. Values are medians;",
        "proof run 1 in each process is discarded as warmup.",
        "",
        "> Comparability note: Jolt's Akita build uses its packed field and cycle-major trace",
        "> order, while Dory uses BN254 and address-major order. The guest, input rule, trace",
        "> cap, compiler, backend mode, protocol stages, machine, and thread cap are fixed.",
        "",
        "## Timing",
        "",
        "| Cycles | Threads | Akita commit (s) | Dory commit (s) | Akita prove (s) | Dory prove (s) | Dory/Akita | Akita verify (ms) | Dory verify (ms) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scale in SCALES:
        for threads in THREADS:
            akita = data.get(("akita", scale, threads))
            dory = data.get(("dory", scale, threads))
            ratio = "--" if not akita or not dory else f"{dory['prove']/akita['prove']:.2f}"
            md.append(
                f"| $2^{{{scale}}}$ | {threads} | {value('akita', scale, threads, 'commit')} "
                f"| {value('dory', scale, threads, 'commit')} | {value('akita', scale, threads, 'prove')} "
                f"| {value('dory', scale, threads, 'prove')} | {ratio} "
                f"| {value('akita', scale, threads, 'verify_ms')} | {value('dory', scale, threads, 'verify_ms')} |"
            )
    md += [
        "",
        "## Proof size and peak prover memory",
        "",
        "| Cycles | Akita proof (KB) | Dory proof (KB) | Akita RSS 1t (GiB) | Akita RSS 8t (GiB) | Dory RSS 1t (GiB) | Dory RSS 8t (GiB) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scale in SCALES:
        md.append(
            f"| $2^{{{scale}}}$ | {value('akita', scale, 1, 'proof_kb')} "
            f"| {value('dory', scale, 1, 'proof_kb')} | {value('akita', scale, 1, 'rss_gib')} "
            f"| {value('akita', scale, 8, 'rss_gib')} | {value('dory', scale, 1, 'rss_gib')} "
            f"| {value('dory', scale, 8, 'rss_gib')} |"
        )
    md += ["", "## Exact commands", ""]
    md.extend(f"```sh\n{command}\n```" for command in commands)
    (root / "report.md").write_text("\n".join(md) + "\n")


def matrix() -> None:
    for scheme in SCHEMES:
        for scale in SCALES:
            for threads in THREADS:
                print(f"{scheme}\tsha2-chain\t2^{scale}\t{threads} threads")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("matrix")
    run = sub.add_parser("run")
    run.add_argument("--source", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--scheme", choices=SCHEMES)
    run.add_argument("--samples", type=int, default=3)
    run.add_argument("--scales", type=int, nargs="+", choices=SCALES, default=SCALES)
    run.add_argument("--threads", type=int, nargs="+", choices=THREADS, default=THREADS)
    run.add_argument("--skip-build", action="store_true")
    compare = sub.add_parser("compare")
    compare.add_argument("results", type=Path)
    args = parser.parse_args()
    if args.action == "matrix":
        matrix()
    elif args.action == "compare":
        render_report(args.results.resolve())
    else:
        source = args.source.resolve()
        out = args.out.resolve()
        verify_source(source)
        schemes = (args.scheme,) if args.scheme else SCHEMES
        out.mkdir(parents=True, exist_ok=True)
        for scheme in schemes:
            first = True
            for scale in args.scales:
                for threads in args.threads:
                    collect_cell(
                        source,
                        out,
                        scheme,
                        scale,
                        threads,
                        args.samples,
                        args.skip_build or not first,
                    )
                    first = False
        render_report(out)


if __name__ == "__main__":
    main()
