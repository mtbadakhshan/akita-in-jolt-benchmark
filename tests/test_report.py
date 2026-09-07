import json
from pathlib import Path

from jolt_pcs_bench import aggregate, commitment_seconds


def test_commitment_seconds_reads_complete_spans(tmp_path: Path) -> None:
    trace = tmp_path / "trace.json"
    trace.write_text(
        json.dumps(
            [
                {"ph": "X", "name": "CommitmentScheme::commit_batch", "dur": 1_250_000},
                {"ph": "B", "name": "commit_witness", "pid": 1, "tid": 2, "ts": 10},
                {"ph": "E", "name": "commit_witness", "pid": 1, "tid": 2, "ts": 500_010},
                {"ph": "X", "name": "unrelated", "dur": 9_000_000},
            ]
        )
    )
    assert commitment_seconds(trace) == 1.75


def test_aggregate_uses_medians() -> None:
    rows = [
        {
            "scheme": "akita",
            "cycles_log2": 20,
            "threads": 1,
            "commit_seconds": n,
            "prove_seconds": n * 2,
            "verify_seconds": n / 1000,
            "proof_bytes": n * 1000,
            "peak_rss_bytes": n * 1024**3,
        }
        for n in (1, 9, 2)
    ]
    result = aggregate(rows)[("akita", 20, 1)]
    assert result["commit"] == 2
    assert result["prove"] == 4
    assert result["verify_ms"] == 2
    assert result["proof_kb"] == 2
    assert result["rss_gib"] == 2
