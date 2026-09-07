from jolt_pcs_bench import aggregate, parse_commit_seconds, parse_duration


def test_span_close_duration_parsing() -> None:
    log = "commit_witness{columns=42}: close time.busy=1.25s time.idle=10.0µs"
    assert parse_commit_seconds(log, "dory") == 1.25
    assert parse_duration("250ms") == 0.25


def test_aggregate_uses_medians() -> None:
    rows = [
        {
            "scheme": "akita",
            "cycles_log2": 20,
            "threads": 1,
            "commit_seconds": n,
            "prove_seconds": n * 2,
            "verify_seconds": n / 1000,
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
    assert result["verify_seconds"] == 0.002
    assert result["proof_bytes"] == 2000
    assert result["peak_rss_bytes"] == 2 * 1024**3
