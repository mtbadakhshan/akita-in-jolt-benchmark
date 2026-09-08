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

SCHEMA_VERSION = 2
REPOSITORY = "https://github.com/a16z/jolt"
JOLT_COMMIT = "7de83dd18839f567e6b88e860d53b0202116654f"
SCALES = (20, 22, 24, 26, 28)
THREADS = (1, 8)
SCHEMES = ("akita", "dory")
COMMIT_STAGE_SPAN = "prove_stage0"
COMMIT_SPAN = {"akita": "akita_main_commit_with_precommitted", "dory": "commit_witness"}
TIMING_COLUMNS = (
    "benchmark_name",
    "scale",
    "prover_time_s",
    "trace_length",
    "proving_hz",
    "proof_size",
    "proof_size_compressed",
    "backend",
    "setup_time_s",
    "verifier_parallel_time_s",
    "verifier_single_thread_time_s",
    "verifier_parallel_threads",
)


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


def rustflags_for(required_isa: str) -> str:
    return f"-C target-cpu=native -C target-feature=+{required_isa}"


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


def environment(threads: int, rustflags: str, source: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "RAYON_NUM_THREADS": str(threads),
            "RUSTFLAGS": rustflags,
            "RUST_LOG": "off",
            "NO_COLOR": "1",
        }
    )
    if source is not None:
        tools = source / "target/benchmark-tools/release"
        env["PATH"] = f"{tools}:{env['PATH']}"
    return env


def build(source: Path, scheme: str, env: dict[str, str]) -> Path:
    tools = source / "target/benchmark-tools"
    cli = tools / "release/jolt"
    if not cli.exists():
        subprocess.run(
            [
                "cargo", "build", "--release", "--locked", "-p", "jolt",
                "--bin", "jolt", "--target-dir", str(tools),
            ],
            cwd=source,
            env=env,
            check=True,
        )
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


def span_busy_times(log: str, name: str) -> list[float]:
    pattern = re.compile(
        r"(?:^|[\s:])"
        + re.escape(name)
        + r"(?:\{[^}]*\})?: close[^\n]*?time\.busy=([0-9.]+(?:ns|µs|us|ms|s))",
        re.M,
    )
    return [parse_duration(value) for value in pattern.findall(log)]


def parse_commit_seconds(log: str, scheme: str) -> float:
    stage = span_busy_times(log, COMMIT_STAGE_SPAN)
    if len(stage) == 1:
        return stage[0]
    if len(stage) > 1:
        return max(stage)
    values = span_busy_times(log, COMMIT_SPAN[scheme])
    if not values:
        raise RuntimeError(f"missing close timing for {COMMIT_STAGE_SPAN} or {COMMIT_SPAN[scheme]}")
    return max(values)


def parse_peak_rss(log: str) -> int:
    match = re.search(r"Peak RSS ([0-9.]+) (B|KiB|MiB|GiB)", log)
    if not match:
        raise RuntimeError("missing upstream Peak RSS metric")
    scale = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}[match.group(2)]
    return round(float(match.group(1)) * scale)


def reported_verify_seconds(threads: int, parallel: float, single: float, verifier_threads: int) -> float | None:
    if threads == 1:
        return single
    if verifier_threads == threads:
        return parallel
    return None


def trace_stem(scheme: str, scale: int) -> str:
    suffix = "_akita" if scheme == "akita" else ""
    return f"modular_sha2_chain{suffix}_{scale}_optimized"


def latest_run(source: Path, scheme: str, scale: int) -> Path | None:
    link = source / "benchmark-runs" / f"latest_{trace_stem(scheme, scale)}"
    if link.exists():
        return link.resolve()
    return None


def clear_profile_locks(source: Path) -> None:
    root = source / "benchmark-runs"
    if not root.exists():
        return
    for path in root.glob("*.lock"):
        path.unlink(missing_ok=True)


def run_directories(source: Path) -> set[Path]:
    root = source / "benchmark-runs"
    return {path for path in root.glob("*") if path.is_dir() and not path.is_symlink()}


def host_os() -> str:
    kernel = platform.release().split("-")[0]
    libc = platform.libc_ver()
    libc_note = f", {libc[0]} {libc[1]}" if libc[0] else ""
    return f"{platform.system()} {kernel} {platform.machine()}{libc_note}"


def rustc_version() -> str:
    lines = []
    for line in command_output("rustc", "-Vv").splitlines():
        key = line.split(":", 1)[0].strip()
        if key in {"rustc", "release", "host", "os", "commit-hash", "llvm version", "binary"}:
            lines.append(line)
    return "\n".join(lines)


def provenance(commit: str, command: str, cpu_list: str | None, required_isa: str, rustflags: str, features: set[str]) -> dict:
    return {
        "utc": datetime.now(timezone.utc).isoformat(),
        "repository": REPOSITORY,
        "branch": "main",
        "jolt_commit": commit,
        "command": command,
        "rustc": rustc_version(),
        "rustflags": rustflags,
        "architecture": platform.machine(),
        "os": host_os(),
        "cpu_model": command_output("bash", "-lc", "lscpu | awk -F: '/Model name/{gsub(/^ +/,\"\",$2); print $2}'")
        if platform.system() == "Linux"
        else command_output("sysctl", "-n", "machdep.cpu.brand_string"),
        "cpu_affinity": cpu_list,
        "required_isa": required_isa,
        "native_target_features": sorted(features),
        "logical_cpus": os.cpu_count(),
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
        "optimized",
    ]
    command, cpu_list = affinity_command(command, threads)
    rustflags = rustflags_for(required_isa)
    env = environment(threads, rustflags, source)
    clear_profile_locks(source)
    before = run_directories(source)
    completed = subprocess.run(command, cwd=source, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log = completed.stdout
    if completed.returncode:
        raise RuntimeError(f"benchmark failed ({completed.returncode}):\n{log[-4000:]}")
    upstream_run = latest_run(source, scheme, scale)
    created = run_directories(source) - before
    if upstream_run is None:
        if len(created) != 1:
            raise RuntimeError(f"expected one upstream run directory, found {sorted(created)}")
        upstream_run = created.pop()
    with (upstream_run / "timings.csv").open(newline="") as stream:
        values = next(csv.reader(stream))
    if len(values) != len(TIMING_COLUMNS):
        raise RuntimeError(f"unexpected upstream timing row with {len(values)} columns")
    row = dict(zip(TIMING_COLUMNS, values, strict=True))
    proof_bytes = int(row["proof_size"])
    if proof_bytes <= 0:
        raise RuntimeError("upstream serialized a zero-byte proof")

    cell = out / "raw" / f"{scheme}-2p{scale}-t{threads}" / f"sample-{sample}"
    cell.mkdir(parents=True, exist_ok=True)
    (cell / "run.log").write_text(log)
    shutil.copy2(upstream_run / "timings.csv", cell / "timings.csv")
    rendered = " ".join(
        [
            f"RUSTFLAGS='{rustflags}'",
            f"RAYON_NUM_THREADS={threads}",
            f"PATH='{source}/target/benchmark-tools/release:$PATH'",
            *command,
        ]
    )
    parallel = float(row["verifier_parallel_time_s"])
    single = float(row["verifier_single_thread_time_s"])
    verifier_threads = int(row["verifier_parallel_threads"])
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
        "verify_seconds": parallel,
        "verify_single_thread_seconds": single,
        "report_verify_seconds": reported_verify_seconds(threads, parallel, single, verifier_threads),
        "verifier_threads": verifier_threads,
        "setup_seconds": float(row["setup_time_s"]),
        "proof_bytes": proof_bytes,
        "peak_rss_bytes": parse_peak_rss(log),
        "verified": True,
        "provenance": provenance(commit, rendered, cpu_list, required_isa, rustflags, features),
    }


def load_records(root: Path) -> list[dict]:
    path = root / "records.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def write_records(root: Path, records: list[dict]) -> None:
    (root / "records.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records))


def report_verify_from_row(row: dict) -> float | None:
    if "report_verify_seconds" in row:
        return row["report_verify_seconds"]
    return reported_verify_seconds(
        row["threads"],
        row["verify_seconds"],
        row["verify_single_thread_seconds"],
        row["verifier_threads"],
    )


def median_optional(values: list[float | None]) -> float | None:
    if not values or any(value is None for value in values):
        return None
    return statistics.median(values)


def aggregate(records: list[dict]) -> dict[tuple[str, int, int], dict]:
    grouped: dict[tuple[str, int, int], list[dict]] = {}
    for row in records:
        if not row["warmup"]:
            grouped.setdefault((row["scheme"], row["cycles_log2"], row["threads"]), []).append(row)
    numeric = ("commit_seconds", "prove_seconds", "setup_seconds", "proof_bytes", "peak_rss_bytes")
    result = {}
    for group, rows in grouped.items():
        result[group] = {key: statistics.median(row[key] for row in rows) for key in numeric}
        result[group]["verify_seconds"] = median_optional([report_verify_from_row(row) for row in rows])
    return result


def fmt(value: float | None, divisor=1.0) -> str:
    return "--" if value is None else f"{value / divisor:.2f}"


def cell(data: dict, scheme: str, scale: int, threads: int, key: str, divisor=1.0) -> str:
    row = data.get((scheme, scale, threads))
    if row is None:
        return "--"
    return fmt(row[key], divisor)


def public_command(command: str) -> str:
    return re.sub(r"(?:/[^\s]+)?/third_party/jolt", "third_party/jolt", command)


def prove_ratio(data: dict, scale: int, threads: int) -> str:
    akita = data.get(("akita", scale, threads))
    dory = data.get(("dory", scale, threads))
    if not akita or not dory:
        return "--"
    return f"{dory['prove_seconds'] / akita['prove_seconds']:.2f}"


def render_markdown(data: dict, records: list[dict]) -> str:
    commit = records[0]["provenance"]["jolt_commit"] if records else JOLT_COMMIT
    isa = records[0]["provenance"]["required_isa"] if records else "AVX-512/NEON"
    commands = sorted({public_command(row["provenance"]["command"]) for row in records})
    machine = ""
    if records:
        row = records[0]["provenance"]
        gib = int(row["memory_bytes"]) / 1024**3
        machine = (
            f"Measurements were collected on a single {row['cpu_model']} "
            f"({row['os']}, {row.get('logical_cpus', '?')} logical CPUs, {gib:.0f} GiB RAM). "
            f"`{row['required_isa']}` was required and activated (`{row['rustflags']}`)."
        )
    lines = [
        "# Akita in Jolt: comparison with Dory",
        "",
        machine,
        "",
        f"Source: `{REPOSITORY}` main at `{commit}`.",
        "All measured proofs completed the upstream full-verification correctness gate.",
        f"Native compilation was required to expose `{isa}`.",
        "Verify(1) is the upstream single-thread pool; Verify(8) is the parallel pool only when it has exactly 8 workers.",
        "",
        "| Cycles | Threads | Akita commit (s) | Dory commit (s) | Akita prove (s) | Dory prove (s) | Dory/Akita | Akita verify (ms) | Dory verify (ms) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scale in SCALES:
        for threads in THREADS:
            lines.append(
                f"| $2^{{{scale}}}$ | {threads} | {cell(data, 'akita', scale, threads, 'commit_seconds')} "
                f"| {cell(data, 'dory', scale, threads, 'commit_seconds')} | {cell(data, 'akita', scale, threads, 'prove_seconds')} "
                f"| {cell(data, 'dory', scale, threads, 'prove_seconds')} | {prove_ratio(data, scale, threads)} "
                f"| {cell(data, 'akita', scale, threads, 'verify_seconds', .001)} "
                f"| {cell(data, 'dory', scale, threads, 'verify_seconds', .001)} |"
            )
    lines += [
        "",
        "| Cycles | Akita proof (KB) | Dory proof (KB) | Akita RSS 1t (GiB) | Akita RSS 8t (GiB) | Dory RSS 1t (GiB) | Dory RSS 8t (GiB) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scale in SCALES:
        lines.append(
            f"| $2^{{{scale}}}$ | {cell(data, 'akita', scale, 1, 'proof_bytes', 1000)} "
            f"| {cell(data, 'dory', scale, 1, 'proof_bytes', 1000)} "
            f"| {cell(data, 'akita', scale, 1, 'peak_rss_bytes', 1024**3)} "
            f"| {cell(data, 'akita', scale, 8, 'peak_rss_bytes', 1024**3)} "
            f"| {cell(data, 'dory', scale, 1, 'peak_rss_bytes', 1024**3)} "
            f"| {cell(data, 'dory', scale, 8, 'peak_rss_bytes', 1024**3)} |"
        )
    lines += ["", "## Exact measured commands", ""]
    lines.extend(f"```sh\n{command}\n```" for command in commands)
    return "\n".join(lines) + "\n"


def render_latex(data: dict) -> str:
    time_rows = []
    for index, scale in enumerate(SCALES):
        if index:
            time_rows.append(r"\addlinespace")
        for threads in THREADS:
            time_rows.append(
                f"$2^{{{scale}}}$ & {threads} & "
                f"{cell(data, 'akita', scale, threads, 'commit_seconds')} & "
                f"{cell(data, 'dory', scale, threads, 'commit_seconds')} & "
                f"{cell(data, 'akita', scale, threads, 'prove_seconds')} & "
                f"{cell(data, 'dory', scale, threads, 'prove_seconds')} & "
                f"{prove_ratio(data, scale, threads)} & "
                f"{cell(data, 'akita', scale, threads, 'verify_seconds', .001)} & "
                f"{cell(data, 'dory', scale, threads, 'verify_seconds', .001)} \\\\"
            )
    resource_rows = []
    for scale in SCALES:
        resource_rows.append(
            f"$2^{{{scale}}}$ & "
            f"{cell(data, 'akita', scale, 1, 'proof_bytes', 1000)} & "
            f"{cell(data, 'dory', scale, 1, 'proof_bytes', 1000)} & "
            f"{cell(data, 'akita', scale, 1, 'peak_rss_bytes', 1024**3)} & "
            f"{cell(data, 'akita', scale, 8, 'peak_rss_bytes', 1024**3)} & "
            f"{cell(data, 'dory', scale, 1, 'peak_rss_bytes', 1024**3)} & "
            f"{cell(data, 'dory', scale, 8, 'peak_rss_bytes', 1024**3)} \\\\"
        )
    time_body = "\n".join(time_rows)
    resource_body = "\n".join(resource_rows)
    return f"""% Generated by jolt_pcs_bench.py. Input from records.jsonl.
\\begin{{table}}[H]
\\centering
\\caption[Jolt timing with Akita and Dory]{{Commitment, end-to-end proving, and
verification time for \\texttt{{sha2-chain}} with Akita and Dory.  A dash
denotes an unsupported parallel mode.}}
\\label{{tab:eval-jolt-time}}
\\scriptsize
\\setlength{{\\tabcolsep}}{{3.5pt}}
\\begin{{tabular}}{{@{{}}rcrrrrrrr@{{}}}}
\\toprule
RISC-V cycles & Threads & \\multicolumn{{2}}{{c}}{{Commit (s)}}
& \\multicolumn{{3}}{{c}}{{Prove (s)}} & \\multicolumn{{2}}{{c}}{{Verify (ms)}} \\\\
\\cmidrule(lr){{3-4}}\\cmidrule(lr){{5-7}}\\cmidrule(lr){{8-9}}
& & Akita & Dory & Akita & Dory & Dory/Akita & Akita & Dory \\\\
\\midrule
{time_body}
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\begin{{table}}[H]
\\centering
\\caption[Jolt communication and memory with Akita and Dory]{{Serialized Jolt
proof size and peak prover memory for the runs in
\\Cref{{tab:eval-jolt-time}}.}}
\\label{{tab:eval-jolt-resources}}
\\small
\\setlength{{\\tabcolsep}}{{7pt}}
\\begin{{tabular}}{{@{{}}rrrrrrr@{{}}}}
\\toprule
RISC-V cycles & \\multicolumn{{2}}{{c}}{{Proof (KB)}}
& \\multicolumn{{2}}{{c}}{{Akita RSS (GiB)}} & \\multicolumn{{2}}{{c}}{{Dory RSS (GiB)}} \\\\
\\cmidrule(lr){{2-3}}\\cmidrule(lr){{4-5}}\\cmidrule(lr){{6-7}}
& Akita & Dory & 1 thread & 8 threads & 1 thread & 8 threads \\\\
\\midrule
{resource_body}
\\bottomrule
\\end{{tabular}}
\\end{{table}}
"""


def write_provenance(root: Path, records: list[dict]) -> None:
    if not records:
        return
    row = records[0]["provenance"]
    (root / "provenance.txt").write_text(
        "\n".join(
            [
                f"repository={row['repository']}",
                f"jolt_commit={row['jolt_commit']}",
                f"architecture={row['architecture']}",
                f"os={row['os']}",
                f"cpu_model={row['cpu_model']}",
                f"logical_cpus={row.get('logical_cpus', '')}",
                f"required_isa={row['required_isa']}",
                f"rustflags={row['rustflags']}",
                f"cpu_affinity={row.get('cpu_affinity')}",
                f"memory_bytes={row['memory_bytes']}",
            ]
        )
        + "\n"
    )


def render_report(root: Path) -> None:
    records = load_records(root)
    data = aggregate(records)
    (root / "report.md").write_text(render_markdown(data, records))
    (root / "report.tex").write_text(render_latex(data))
    write_provenance(root, records)


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
        for scale in SCALES:
            for threads in THREADS:
                for scheme in SCHEMES:
                    print(f"{scheme}\tsha2-chain\t2^{scale}\t{threads} threads")
        return
    if args.action == "compare":
        render_report(args.results.resolve())
        return
    source, out = args.source.resolve(), args.out.resolve()
    commit = verify_source(source)
    required_isa, features = native_features()
    rustflags = rustflags_for(required_isa)
    out.mkdir(parents=True, exist_ok=True)
    records = load_records(out)
    completed = {
        (row["scheme"], row["cycles_log2"], row["threads"], row["sample"])
        for row in records
        if row.get("status") == "ok"
    }
    schemes = (args.scheme,) if args.scheme else SCHEMES
    binaries = {
        scheme: build(source, scheme, environment(max(args.threads), rustflags, source))
        for scheme in schemes
    }
    for scale in args.scales:
        for threads in args.threads:
            for sample in range(args.samples + 1):
                for scheme in schemes:
                    identity = (scheme, scale, threads, sample)
                    if identity in completed:
                        continue
                    record = run_sample(
                        source, binaries[scheme], out, commit, required_isa, features,
                        scheme, scale, threads, sample,
                    )
                    records.append(record)
                    completed.add(identity)
                    write_records(out, records)
    render_report(out)


if __name__ == "__main__":
    main()
