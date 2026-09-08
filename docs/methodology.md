# Methodology

1. Every measured proof must serialize to nonzero bytes and verify.
2. The source is `https://github.com/a16z/jolt`. `scripts/fetch-jolt.sh`
   defaults to the SHA in `results/jolt-x86_64` (`7de83dd18839f567e6b88e860d53b0202116654f`)
   and detaches there. Pass `main` or `latest` for tip of `origin/main`, or pass
   another SHA to pin it. Every observation records the resolved commit.
3. The upstream modular `jolt-prover profile` harness supplies the guest,
   deterministic `sha2-chain` input, trace cap, packaged Akita planner
   schedules, setup, serialization, and full-verification gate. The two
   binaries are the same tree with `profiling,akita` versus `profiling`.
4. Each sample is a fresh process. Sample 0 is warmup; measured values are
   the median of samples 1 through 3. Akita and Dory samples of the same
   (scale, threads, sample) index run back-to-back in one session.
5. `RAYON_NUM_THREADS` is fixed to the row's 1- or 8-thread cap. Linux rows
   are also pinned with `taskset` to that many CPUs.
6. Raw responses, traces, logs, commands, provenance, JSONL, Markdown, and
   LaTeX (`report.tex`) are retained.
7. Builds use `-C target-cpu=native` plus an explicit ISA feature: `avx512f`
   on x86_64, `neon` on Apple Silicon (`arm64`/`aarch64`). The run refuses to
   start if native compilation does not expose that feature. Architectures
   never form ratios.

## Jolt protocol pairing

Jolt compiles one protocol per binary. Replacing Dory with Akita selects the
packed field, cycle-major representation, packaged planner schedules, and
the matching PIOP. That pairing is the experiment, not a defect: same guest,
input, padded trace cap, compiler, optimized backend, machine, and CPU
affinity; different PCS and the PIOP Jolt uses with that PCS.

## Timing boundaries

Input generation, guest tracing, and non-PCS preprocessing are outside
`prove_seconds`. The prove interval includes witness materialization,
commitment, all sumchecks, and the final PCS opening.

`commit_seconds` is the `prove_stage0` span-close `time.busy` (the stage that
commits the Jolt opening instances). If that span is absent, the scheme
commit seam is used and parallel instances take the max, not the sum.

`verify_seconds` in the report is the upstream single-thread verifier pool
on 1-thread rows. On 8-thread rows it is the upstream parallel verifier pool
only when that pool has exactly eight workers (Linux `taskset` to eight
CPUs). Otherwise the cell is a dash: unsupported or uncontrolled parallel
mode. PCS setup is timed separately and is not in the paper tables.

Peak RSS is the upstream process high-water mark from the same profile
child, including guest compile and trace. Proof bytes are the upstream
bincode size of the serialized Jolt proof.

## Statistics

The default expensive-run policy is one warmup and three measured proofs per
cell. Reports use medians and preserve all observations. Increase `--samples`
for a publication final if machine time permits. Headline paper numbers
should be collected on the same Linux x86_64 AVX-512 machine as the PCS
tables. Apple Silicon NEON is a separate result set.
