from jolt_pcs_bench import (
    aggregate,
    parse_commit_seconds,
    parse_duration,
    public_command,
    render_latex,
    reported_verify_seconds,
    rustflags_for,
)


def test_public_command_strips_absolute_source_prefix() -> None:
    command = (
        "PATH='/home/user/akita-in-jolt-benchmark/third_party/jolt/target/benchmark-tools/release:$PATH' "
        "taskset -c 0 /home/user/akita-in-jolt-benchmark/third_party/jolt/target/benchmark-akita/release/jolt-prover "
        "profile --name sha2-chain --scale 20 --format default --backend optimized"
    )
    published = public_command(command)
    assert "/home/" not in published
    assert "third_party/jolt/target/benchmark-akita/release/jolt-prover" in published


def test_isa_rustflags() -> None:
    assert rustflags_for("neon") == "-C target-cpu=native -C target-feature=+neon"
    assert rustflags_for("avx512f") == "-C target-cpu=native -C target-feature=+avx512f"


def test_span_close_duration_parsing() -> None:
    log = "commit_witness{columns=42}: close time.busy=1.25s time.idle=10.0µs"
    assert parse_commit_seconds(log, "dory") == 1.25
    assert parse_duration("250ms") == 0.25


def test_commit_prefers_stage0_wall_clock() -> None:
    log = "\n".join(
        [
            "INFO jolt_prover::prove:prove_stage0:akita_main_commit_with_precommitted: close time.busy=400ms time.idle=0s",
            "INFO jolt_prover::prove:prove_stage0: close time.busy=1.50s time.idle=10ms",
            "INFO jolt_prover::prove:prove_stage0:commit_witness: close time.busy=9s time.idle=0s",
        ]
    )
    assert parse_commit_seconds(log, "akita") == 1.5
    assert parse_commit_seconds(log, "dory") == 1.5


def test_commit_fallback_uses_max_not_sum() -> None:
    log = "\n".join(
        [
            "commit_witness{columns=1}: close time.busy=1.00s time.idle=0s",
            "commit_witness{columns=2}: close time.busy=1.25s time.idle=0s",
        ]
    )
    assert parse_commit_seconds(log, "dory") == 1.25


def test_eight_thread_verify_is_dash_unless_pool_is_exactly_eight() -> None:
    assert reported_verify_seconds(1, 0.008, 0.020, 16) == 0.020
    assert reported_verify_seconds(8, 0.008, 0.020, 8) == 0.008
    assert reported_verify_seconds(8, 0.008, 0.020, 16) is None


def test_aggregate_uses_medians() -> None:
    rows = [
        {
            "scheme": "akita",
            "cycles_log2": 20,
            "threads": 1,
            "commit_seconds": n,
            "prove_seconds": n * 2,
            "verify_seconds": n / 1000,
            "verify_single_thread_seconds": n / 500,
            "report_verify_seconds": n / 500,
            "verifier_threads": 1,
            "setup_seconds": n / 10,
            "proof_bytes": n * 1000,
            "peak_rss_bytes": n * 1024**3,
            "warmup": False,
        }
        for n in (1, 9, 2)
    ]
    result = aggregate(rows)[("akita", 20, 1)]
    assert result["commit_seconds"] == 2
    assert result["prove_seconds"] == 4
    assert result["verify_seconds"] == 0.004
    assert result["proof_bytes"] == 2000
    assert result["peak_rss_bytes"] == 2 * 1024**3


def test_latex_matches_paper_tables() -> None:
    data = {
        ("akita", 20, 1): {
            "commit_seconds": 1.0,
            "prove_seconds": 2.0,
            "verify_seconds": 0.004,
            "proof_bytes": 12000,
            "peak_rss_bytes": 2 * 1024**3,
        },
        ("dory", 20, 1): {
            "commit_seconds": 3.0,
            "prove_seconds": 6.0,
            "verify_seconds": 0.008,
            "proof_bytes": 34000,
            "peak_rss_bytes": 4 * 1024**3,
        },
        ("akita", 20, 8): {
            "commit_seconds": 0.5,
            "prove_seconds": 1.0,
            "verify_seconds": None,
            "proof_bytes": 12000,
            "peak_rss_bytes": 3 * 1024**3,
        },
        ("dory", 20, 8): {
            "commit_seconds": 1.5,
            "prove_seconds": 3.0,
            "verify_seconds": 0.003,
            "proof_bytes": 34000,
            "peak_rss_bytes": 5 * 1024**3,
        },
    }
    tex = render_latex(data)
    assert r"\label{tab:eval-jolt-time}" in tex
    assert r"\label{tab:eval-jolt-resources}" in tex
    assert r"$2^{20}$ & 1 & 1.00 & 3.00 & 2.00 & 6.00 & 3.00 & 4.00 & 8.00 \\" in tex
    assert r"$2^{20}$ & 8 & 0.50 & 1.50 & 1.00 & 3.00 & 3.00 & -- & 3.00 \\" in tex
    assert r"$2^{20}$ & 12.00 & 34.00 & 2.00 & 3.00 & 4.00 & 5.00 \\" in tex
    assert r"$2^{28}$ & -- & -- & -- & -- & -- & -- \\" in tex
