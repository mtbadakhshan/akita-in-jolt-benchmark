# Akita in Jolt: comparison with Dory

Measurements were collected on a single AMD Ryzen 9 9950X 16-Core Processor (Linux 7.0.0 x86_64, glibc 2.43, 32 logical CPUs, 121 GiB RAM). `avx512f` was required and activated (`-C target-cpu=native -C target-feature=+avx512f`).

Source: `https://github.com/a16z/jolt` main at `7de83dd18839f567e6b88e860d53b0202116654f`.
All measured proofs completed the upstream full-verification correctness gate.
Native compilation was required to expose `avx512f`.
Verify(1) is the upstream single-thread pool; Verify(8) is the parallel pool only when it has exactly 8 workers.

| Cycles | Threads | Akita commit (s) | Dory commit (s) | Akita prove (s) | Dory prove (s) | Dory/Akita | Akita verify (ms) | Dory verify (ms) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| $2^{20}$ | 1 | 2.29 | 12.60 | 9.09 | 30.44 | 3.35 | 16.33 | 71.92 |
| $2^{20}$ | 8 | 0.42 | 2.01 | 1.74 | 4.69 | 2.70 | 10.78 | 58.50 |
| $2^{22}$ | 1 | 8.94 | 33.40 | 34.01 | 88.54 | 2.60 | 13.55 | 76.00 |
| $2^{22}$ | 8 | 1.55 | 5.15 | 6.36 | 13.51 | 2.12 | 10.30 | 62.59 |
| $2^{24}$ | 1 | 35.30 | 98.00 | 126.00 | 284.13 | 2.25 | 17.75 | 80.02 |
| $2^{24}$ | 8 | 5.79 | 14.80 | 23.07 | 42.93 | 1.86 | 12.05 | 66.26 |
| $2^{26}$ | 1 | 113.00 | 267.00 | 390.26 | 913.44 | 2.34 | 34.05 | 83.36 |
| $2^{26}$ | 8 | 15.90 | 52.40 | 68.72 | 149.71 | 2.18 | 21.71 | 77.48 |
| $2^{28}$ | 1 | 450.00 | 835.00 | 1467.22 | 3005.05 | 2.05 | 46.39 | 87.04 |
| $2^{28}$ | 8 | 63.30 | 203.00 | 254.54 | 534.87 | 2.10 | 27.29 | 80.01 |

| Cycles | Akita proof (KB) | Dory proof (KB) | Akita RSS 1t (GiB) | Akita RSS 8t (GiB) | Dory RSS 1t (GiB) | Dory RSS 8t (GiB) |
|---:|---:|---:|---:|---:|---:|---:|
| $2^{20}$ | 89.51 | 87.10 | 0.51 | 0.65 | 0.36 | 0.44 |
| $2^{22}$ | 93.50 | 91.44 | 1.14 | 1.35 | 1.31 | 1.27 |
| $2^{24}$ | 96.10 | 95.77 | 3.94 | 3.85 | 4.15 | 4.20 |
| $2^{26}$ | 96.75 | 92.56 | 12.80 | 13.02 | 14.69 | 15.24 |
| $2^{28}$ | 98.54 | 96.63 | 43.80 | 44.63 | 52.81 | 54.19 |

## Exact measured commands

```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=1 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0 third_party/jolt/target/benchmark-akita/release/jolt-prover profile --name sha2-chain --scale 20 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=1 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0 third_party/jolt/target/benchmark-akita/release/jolt-prover profile --name sha2-chain --scale 22 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=1 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0 third_party/jolt/target/benchmark-akita/release/jolt-prover profile --name sha2-chain --scale 24 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=1 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0 third_party/jolt/target/benchmark-akita/release/jolt-prover profile --name sha2-chain --scale 26 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=1 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0 third_party/jolt/target/benchmark-akita/release/jolt-prover profile --name sha2-chain --scale 28 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=1 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0 third_party/jolt/target/benchmark-dory/release/jolt-prover profile --name sha2-chain --scale 20 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=1 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0 third_party/jolt/target/benchmark-dory/release/jolt-prover profile --name sha2-chain --scale 22 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=1 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0 third_party/jolt/target/benchmark-dory/release/jolt-prover profile --name sha2-chain --scale 24 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=1 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0 third_party/jolt/target/benchmark-dory/release/jolt-prover profile --name sha2-chain --scale 26 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=1 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0 third_party/jolt/target/benchmark-dory/release/jolt-prover profile --name sha2-chain --scale 28 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=8 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0,1,2,3,4,5,6,7 third_party/jolt/target/benchmark-akita/release/jolt-prover profile --name sha2-chain --scale 20 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=8 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0,1,2,3,4,5,6,7 third_party/jolt/target/benchmark-akita/release/jolt-prover profile --name sha2-chain --scale 22 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=8 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0,1,2,3,4,5,6,7 third_party/jolt/target/benchmark-akita/release/jolt-prover profile --name sha2-chain --scale 24 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=8 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0,1,2,3,4,5,6,7 third_party/jolt/target/benchmark-akita/release/jolt-prover profile --name sha2-chain --scale 26 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=8 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0,1,2,3,4,5,6,7 third_party/jolt/target/benchmark-akita/release/jolt-prover profile --name sha2-chain --scale 28 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=8 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0,1,2,3,4,5,6,7 third_party/jolt/target/benchmark-dory/release/jolt-prover profile --name sha2-chain --scale 20 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=8 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0,1,2,3,4,5,6,7 third_party/jolt/target/benchmark-dory/release/jolt-prover profile --name sha2-chain --scale 22 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=8 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0,1,2,3,4,5,6,7 third_party/jolt/target/benchmark-dory/release/jolt-prover profile --name sha2-chain --scale 24 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=8 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0,1,2,3,4,5,6,7 third_party/jolt/target/benchmark-dory/release/jolt-prover profile --name sha2-chain --scale 26 --format default --backend optimized
```
```sh
RUSTFLAGS='-C target-cpu=native -C target-feature=+avx512f' RAYON_NUM_THREADS=8 PATH='third_party/jolt/target/benchmark-tools/release:$PATH' taskset -c 0,1,2,3,4,5,6,7 third_party/jolt/target/benchmark-dory/release/jolt-prover profile --name sha2-chain --scale 28 --format default --backend optimized
```
