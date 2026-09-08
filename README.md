# Akita in Jolt benchmark

End-to-end Jolt comparison of Akita and Dory, in the same style as the PCS
harness in `akita-benchmark`: pinned source, one process per sample, JSONL
as source of truth, Markdown and LaTeX regenerated from it.

Jolt compiles one protocol per binary. The Akita build is packed-field plus
the matching PIOP and planner schedules; Dory is BN254 plus the homomorphic
PIOP. Guest, input, padded cycle cap, compiler, and machine stay fixed.

- padded RISC-V cycle caps: `2^20`, `2^22`, `2^24`, `2^26`, `2^28`;
- Rayon thread caps: 1 and 8;
- PCS builds: `profiling,akita` and `profiling` (Dory);
- one discarded warmup plus three measured proof children per cell.

ISA: x86_64 must expose **AVX-512F**; Apple Silicon must expose **NEON**.
The harness refuses to run otherwise. Do not form ratios across those
machines.

## Headline results (Linux x86_64)

Headline numbers in this repository were collected on one **Linux x86_64**
AVX-512 machine (AMD Ryzen 9 9950X, 32 logical CPUs, 121 GiB RAM). Guest is
`sha2-chain`. Source is [`a16z/jolt`](https://github.com/a16z/jolt) at
[`7de83dd18839f567e6b88e860d53b0202116654f`](https://github.com/a16z/jolt/commit/7de83dd18839f567e6b88e860d53b0202116654f).
Cells are medians of three measured processes after one warmup. Verify(1) is
Jolt’s single-thread pool; Verify(8) is the parallel pool with exactly eight
workers (`taskset` to eight CPUs).

Checked-in JSONL, Markdown, and LaTeX live in
[`results/jolt-x86_64/`](results/jolt-x86_64/report.md).

| Cycles | Threads | Akita commit (s) | Dory commit (s) | Akita prove (s) | Dory prove (s) | Dory/Akita | Akita verify (ms) | Dory verify (ms) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2^20 | 1 | 2.29 | 12.60 | 9.09 | 30.44 | 3.35 | 16.33 | 71.92 |
| 2^20 | 8 | 0.42 | 2.01 | 1.74 | 4.69 | 2.70 | 10.78 | 58.50 |
| 2^22 | 1 | 8.94 | 33.40 | 34.01 | 88.54 | 2.60 | 13.55 | 76.00 |
| 2^22 | 8 | 1.55 | 5.15 | 6.36 | 13.51 | 2.12 | 10.30 | 62.59 |
| 2^24 | 1 | 35.30 | 98.00 | 126.00 | 284.13 | 2.25 | 17.75 | 80.02 |
| 2^24 | 8 | 5.79 | 14.80 | 23.07 | 42.93 | 1.86 | 12.05 | 66.26 |
| 2^26 | 1 | 113.00 | 267.00 | 390.26 | 913.44 | 2.34 | 34.05 | 83.36 |
| 2^26 | 8 | 15.90 | 52.40 | 68.72 | 149.71 | 2.18 | 21.71 | 77.48 |
| 2^28 | 1 | 450.00 | 835.00 | 1467.22 | 3005.05 | 2.05 | 46.39 | 87.04 |
| 2^28 | 8 | 63.30 | 203.00 | 254.54 | 534.87 | 2.10 | 27.29 | 80.01 |

| Cycles | Akita proof (KB) | Dory proof (KB) | Akita RSS 1t (GiB) | Akita RSS 8t (GiB) | Dory RSS 1t (GiB) | Dory RSS 8t (GiB) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2^20 | 89.51 | 87.10 | 0.51 | 0.65 | 0.36 | 0.44 |
| 2^22 | 93.50 | 91.44 | 1.14 | 1.35 | 1.31 | 1.27 |
| 2^24 | 96.10 | 95.77 | 3.94 | 3.85 | 4.15 | 4.20 |
| 2^26 | 96.75 | 92.56 | 12.80 | 13.02 | 14.69 | 15.24 |
| 2^28 | 98.54 | 96.63 | 43.80 | 44.63 | 52.81 | 54.19 |

## Reproduce

```sh
./scripts/fetch-jolt.sh third_party/jolt                 # paper SHA
# ./scripts/fetch-jolt.sh third_party/jolt latest         # tip of origin/main
python3 jolt_pcs_bench.py matrix
python3 jolt_pcs_bench.py run \
  --source third_party/jolt \
  --out results/jolt-x86_64
```

On Apple Silicon use a separate output directory, for example
`results/jolt-arm64`. To render an existing result set without rerunning:

```sh
python3 jolt_pcs_bench.py compare results/jolt-x86_64
```

That writes `report.md`, `report.tex`, and `provenance.txt`. The fetch
detaches at the resolved SHA. Every record captures that commit. Each raw
sample retains the upstream timing CSV and complete span-close log.

## What is measured

- `prove_seconds`: upstream Jolt's modular proof call, including witness
  materialization, commitment, all sumchecks, and final PCS opening;
- `commit_seconds`: upstream `prove_stage0` wall-clock (Jolt opening commits);
- `verify_seconds` in the tables: 1-thread pool on 1-thread rows; 8-worker
  parallel pool on 8-thread rows (Linux `taskset`), otherwise a dash;
- `proof_bytes`: upstream exact serialized proof-size metric;
- `peak_rss_bytes`: upstream process peak-RSS metric;
- `setup_seconds`: upstream PCS setup measurement (not in the paper tables).

See [docs/methodology.md](docs/methodology.md).
