# Verification snapshot — 27 October 2026

## Demonstration configuration

- Hardware: Mac, Apple M4 Pro, 24 GB unified memory; MPS float32 inference.
- Model: `meta-llama/Llama-3.2-1B-Instruct` with the official
  `AvaLovelace/BrickGPT` LoRA adapter, using the source and weight revisions in the README.
- Solver: Gurobi 13.0.3, executing the official static force/torque formulation
  and physics-informed rollback. The teammate's RTX 5060/HiGHS experiment is separate.

## Successful full-pipeline result

- Original geometry/stability tests:13/13pass.
- Real local API plus optional solver tests:14/14pass, including a connected but
  force-unstable stack and the original stable-prefix rollback implementation.
- Fresh official-weight MPS float32 inference, seed42, paper table prompt, original
  Gurobi13.0.3: first draft174bricks failed; one rollback retained3bricks; final
  output113bricks passed geometry and static force checks. Generation402.26seconds.
- The174brick comparison is extracted from the same inference trace at its first
  EOS and analyzed with Gurobi. It is not represented as a separately sampled run.
- This executes the original generation, rejection, force-model and rollback path.
  It does not reproduce the authors' hardware timing, all250evaluation prompts,
  Blender/FlashTex rendering, physical assembly or robot control.

## Earlier connectivity-only package checks

These records cover saved-output packaging and connectivity checks; the successful
Mac/Gurobi full-pipeline demonstration above is the presentation example.

### Distribution and replay

- Eight standard-library integration tests passed against the actual loopback API.
- A separate clean export of the staged files passed all eight tests using Python
  with site packages disabled (`-S`). No weights, local manifest, upstream checkout,
  virtual environment or extra Python package was present in that export.
- The clean export started successfully, automatically selected replay-only mode and
  exposed exactly the two shipped reference runs. Its temporary server was stopped.
- Browser checks confirmed model identity, disabled generation in replay-only mode,
  saved output rendering and the assembly replay control.
- Python compilation, JavaScript syntax and shell syntax checks passed.
- The publication file list was checked for common credential patterns, private home
  paths and accidentally included weights/environments. No matches were found. This
  is a bounded publication check, not a general security certification.

### Separate packaging inference

The packaged runner was executed with the pinned official source and already-cached
official weights in the existing isolated ML environment on Apple M4 Pro (24 GB),
Python 3.12.14, PyTorch 2.7.0, Transformers 4.51.3 and PEFT 0.15.2.

| Item | Observed |
|---|---|
| Prompt | A high-backed chair with four legs and a flat seat. |
| Seed / device / dtype | 42 / MPS / float32 |
| Bricks / generation time | 72 / 121.46 seconds (loading excluded) |
| Rejections / rollbacks | 45 / 0 |
| Official adapter attached / EOS | yes / yes |
| Bounds / collisions / ground connectivity | pass / pass / pass |
| Static force stability | not certified for this connectivity-only run |
| Preview / GLB / MP4 export | completed |
| Decoded TXT SHA-256 | `fd84e07a1c65cfb92df8124eff8cd789013bc5ecd92cf4d1710cf5758ee92aa7` |

The TXT hash matches the shipped 86.01-second chair run despite the different elapsed
time. The additional packaging run remains a local ignored output; its model weights
and local configuration are not part of the repository.

This validates the package's inference path using the existing ML environment and
cache. It is not a fresh installation of all ML dependencies, a CUDA/CPU/WSL test,
a quality benchmark, a full physics validation or a reproduction of the paper's metrics.
