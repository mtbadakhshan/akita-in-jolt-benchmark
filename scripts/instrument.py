#!/usr/bin/env python3
"""Apply the small, pinned daemon telemetry instrumentation."""

from pathlib import Path
import sys


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if text.count(old) != 1:
        raise SystemExit(f"expected exactly one instrumentation anchor in {path}")
    path.write_text(text.replace(old, new))


root = Path(sys.argv[1])
proto = root / "examples-rs/prover-daemon/proto/prover.proto"
types = root / "examples-rs/prover-daemon/src/types.rs"
prove = root / "examples-rs/prover-daemon/src/prove_modular.rs"

replace_once(
    proto,
    "  optional string details = 12;\n}",
    """  optional string details = 12;

  // Benchmark telemetry measured inside the isolated proof child.
  optional double verify_duration_secs = 13;
  optional double total_duration_secs = 14;
  optional uint64 peak_rss_bytes = 15;
}""",
)
replace_once(
    types,
    "    pub proof_size_bytes: Option<usize>,\n",
    """    pub proof_size_bytes: Option<usize>,
    pub verify_duration_secs: Option<f64>,
    pub total_duration_secs: Option<f64>,
    pub peak_rss_bytes: Option<u64>,
""",
)
replace_once(
    types,
    "            proof_size_bytes: Some(proof_size_bytes),\n",
    """            proof_size_bytes: Some(proof_size_bytes),
            verify_duration_secs: None,
            total_duration_secs: None,
            peak_rss_bytes: None,
""",
)
replace_once(
    types,
    "    pub fn error(msg: impl Into<String>) -> Self {\n",
    """    pub fn with_benchmark_metrics(
        mut self,
        verify_duration_secs: f64,
        total_duration_secs: f64,
        peak_rss_bytes: u64,
    ) -> Self {
        self.verify_duration_secs = Some(verify_duration_secs);
        self.total_duration_secs = Some(total_duration_secs);
        self.peak_rss_bytes = Some(peak_rss_bytes);
        self
    }

    pub fn error(msg: impl Into<String>) -> Self {
""",
)
replace_once(
    types,
    "            proof_size_bytes: None,\n",
    """            proof_size_bytes: None,
            verify_duration_secs: None,
            total_duration_secs: None,
            peak_rss_bytes: None,
""",
)
replace_once(
    types,
    "            details: r.details,\n",
    """            details: r.details,
            verify_duration_secs: r.verify_duration_secs,
            total_duration_secs: r.total_duration_secs,
            peak_rss_bytes: r.peak_rss_bytes,
""",
)
replace_once(
    prove,
    '        tracing::info!("Verifying proof...");\n',
    """        tracing::info!("Verifying proof...");
        let verify_start = Instant::now();
""",
)
replace_once(
    prove,
    "        let total_duration = start.elapsed().as_secs_f64();\n",
    """        let verify_duration = verify_start.elapsed().as_secs_f64();

        let total_duration = start.elapsed().as_secs_f64();
""",
)
replace_once(
    prove,
    "        ProofResponse::success(prove_duration, verified, proof_size, artifacts)\n",
    """        ProofResponse::success(prove_duration, verified, proof_size, artifacts)
            .with_benchmark_metrics(
                verify_duration,
                total_duration,
                peak_rss_bytes().unwrap_or(0),
            )
""",
)
prove.write_text(
    prove.read_text().rstrip()
    + """

/// Linux process high-water RSS from `/proc`, in bytes.
fn peak_rss_bytes() -> Option<u64> {
    let status = std::fs::read_to_string("/proc/self/status").ok()?;
    let line = status.lines().find(|line| line.starts_with("VmHWM:"))?;
    let kib = line.split_whitespace().nth(1)?.parse::<u64>().ok()?;
    kib.checked_mul(1024)
}
"""
)
