# Akita in Jolt benchmark

Publication-oriented benchmark of Jolt's serialized, verified `sha2-chain`
proofs with Akita and Dory. The matrix is:

- padded RISC-V cycle caps: `2^20`, `2^22`, `2^24`, `2^26`, `2^28`;
- Rayon thread caps: 1 and 8;
- PCS builds: `akita-pcs` and `dory-pcs`;
- one discarded warmup plus three measured proof children per cell.

Raw JSONL is the source of truth. Markdown is regenerated from it.

## Reproduce

```sh
./scripts/bootstrap-protoc.sh
./scripts/fetch-jolt.sh third_party/jolt-cpp
python3 jolt_pcs_bench.py matrix
python3 jolt_pcs_bench.py run \
  --source third_party/jolt-cpp \
  --out results/jolt-x86_64
```

To render an existing result set without rerunning:

```sh
python3 jolt_pcs_bench.py compare results/jolt-x86_64
```

Each raw cell contains `command.txt`, the complete integration log, gRPC
responses, Chrome traces, and measured JSONL. The generated report repeats
every exact benchmark command.

## What is measured

- `prove_seconds`: Jolt's modular proof call, including witness
  materialization, commitment, all sumchecks, and final PCS opening;
- `commit_seconds`: commitment spans inside that proof call;
- `verify_seconds`: deserialize plus full Jolt verification;
- `proof_bytes`: the serialized Jolt proof returned by the daemon;
- `peak_rss_bytes`: the proof child's Linux `VmHWM`;
- `total_seconds`: request handling through verification and artifact creation.

See [docs/methodology.md](docs/methodology.md) for comparability constraints.
