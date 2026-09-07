# Methodology

1. Every measured proof must serialize to nonzero bytes and verify.
2. The source is `https://github.com/a16z/jolt`. `main` is resolved once, then
   detached; its exact SHA is retained in every observation.
3. The upstream modular `jolt-prover profile` harness supplies the guest,
   deterministic `sha2-chain` input, trace cap, setup, serialization, and
   full-verification gate.
4. Each sample is a fresh process. Sample 0 is warmup; measured values are
   the median of samples 1 through 3.
5. `RAYON_NUM_THREADS` is fixed to the row's 1- or 8-thread cap.
6. Raw responses, traces, logs, commands, provenance, and JSONL are retained.
7. Akita and Dory cells run on the same physical machine in one session.
8. `RUSTFLAGS=-C target-cpu=native` is fixed. x86_64 runs must expose
   `avx512f`; Apple Silicon runs must expose `neon`. The native feature set is
   recorded, and results from different architectures never form ratios.

## Comparability limitation

This is an integration comparison, not a bit-identical PCS microbenchmark.
Jolt's Akita feature selects the packed field and cycle-major representation;
Dory selects BN254 and its homomorphic representation. The upstream profile
harness fixes the guest, input rule, trace cap, reference backend tier,
protocol stages, machine, compiler, and CPU affinity.

## Timing boundaries

Input generation, guest tracing, and non-PCS preprocessing are outside
`prove_seconds`. The prove interval includes witness materialization,
commitment, all sumchecks, and the final PCS opening. PCS setup, parallel
verification, and single-thread verification are timed separately upstream.

The upstream `default` tracing format emits span-close timings without
retaining enormous Chrome traces. `commit_seconds` uses `commit_witness` for
Dory and `akita_main_commit_with_precommitted` for Akita. Peak RSS and exact
proof bytes are the upstream profile harness's own metrics.

## Statistics

The default expensive-run policy is one warmup and three measured proofs per
cell. Reports use medians and preserve all observations. Increase `--samples`
for a publication final if machine time permits.
