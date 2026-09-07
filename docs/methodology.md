# Methodology

1. Every measured proof must serialize to nonzero bytes and verify.
2. Jolt and its nested Jolt dependency are immutable commit pins.
3. The guest ELF is identical across cells. Only its declared trace cap and
   deterministic `sha2-chain` iteration input change with the cycle row.
4. Each proof runs in a forked child. Proof 1 is warmup; measured values are
   the median of proofs 2 through 4.
5. `RAYON_NUM_THREADS` is fixed to the row's 1- or 8-thread cap.
6. Raw responses, traces, logs, commands, provenance, and JSONL are retained.
7. Akita and Dory cells run on the same physical machine in one session.

## Comparability limitation

This is an integration comparison, not a bit-identical PCS microbenchmark.
Jolt's Akita feature selects the packed Akita field and cycle-major trace
polynomial order. Its Dory feature selects BN254 and address-major order.
Those differences are required by the current integrations and must be stated
with every headline table. Guest code, deterministic input rule, trace cap,
compiler, committed-program mode, Rust-only backend, Jolt protocol stages,
machine, and thread cap are held fixed.

## Timing boundaries

Input generation, guest tracing, daemon startup, PCS setup, and reusable
program preprocessing are outside `prove_seconds`. The prove interval includes
Jolt witness materialization, opening-instance commitment, all sumchecks, and
the final PCS opening. Verification is separately timed after serializing and
deserializing the proof.

Chrome tracing is enabled for both implementations so commitment spans are
measured under the same instrumentation. `commit_seconds` sums the
backend-neutral stage-0 commitment spans. `peak_rss_bytes` is Linux `VmHWM`
read in the isolated proof child after verification.

## Statistics

The default expensive-run policy is one warmup and three measured proofs per
cell. Reports use medians and preserve all observations. Increase `--samples`
for a publication final if machine time permits.
