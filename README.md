# Akita in Jolt benchmark

Publication-oriented benchmark of the latest `main` branch of
[`a16z/jolt`](https://github.com/a16z/jolt). It compares the upstream modular
prover's serialized, verified `sha2-chain` proofs with Akita and Dory.

- padded RISC-V cycle caps: `2^20`, `2^22`, `2^24`, `2^26`, `2^28`;
- Rayon thread caps: 1 and 8;
- PCS builds: `akita-pcs` and `dory-pcs`;
- one discarded warmup plus three measured proof children per cell.

Raw JSONL is the source of truth. Markdown is regenerated from it.

## Reproduce

```sh
./scripts/fetch-jolt.sh third_party/jolt
python3 jolt_pcs_bench.py matrix
python3 jolt_pcs_bench.py run \
  --source third_party/jolt \
  --out results/jolt-x86_64
```

To render an existing result set without rerunning:

```sh
python3 jolt_pcs_bench.py compare results/jolt-x86_64
```

The fetch resolves `main` once and detaches at that SHA. Every record captures
the resolved commit. Each raw sample retains the upstream timing CSV and
complete span-close log; the generated report repeats every exact measured
command.

## What is measured

- `prove_seconds`: upstream Jolt's modular proof call, including witness
  materialization, commitment, all sumchecks, and final PCS opening;
- `commit_seconds`: upstream stage-0 commitment span;
- `verify_seconds`: upstream full-verification correctness gate;
- `proof_bytes`: upstream exact serialized proof-size metric;
- `peak_rss_bytes`: upstream process peak-RSS metric;
- `setup_seconds`: upstream PCS setup measurement.

On x86_64, runs fail unless native compilation exposes AVX-512F. On a future
Apple Silicon run, the equivalent gate requires NEON. Architectures must be
reported separately.

See [docs/methodology.md](docs/methodology.md) for comparability constraints.
