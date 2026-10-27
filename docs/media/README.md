# Report media provenance

## Rollback-on table video

- Original video: [table-rollback-on.mp4](table-rollback-on.mp4)
- README animation: [table-rollback-on.gif](table-rollback-on.gif), derived from that video at 800 pixels wide and 12 fps, looping.
- Original file: `demo/runs/live-20261027-075703-106000/assembly_replay.mp4`
- Prompt: `Table featuring a flat rectangular surface over four evenly spaced legs.`
- Seed: 42; rollback: on; solver: Gurobi 13.0.3.
- Generation: Apple M4 Pro, MPS float32, official Llama-3.2-1B-Instruct base and BrickGPT LoRA pinned in the main README.
- Completed output: 113 bricks, geometry PASS, static-force PASS.
- One rollback: 174 bricks reduced to a stable prefix of 3, then generation continued.
- Generation time for this run: 400.727 seconds, excluding loading and rendering.
- This video animates the saved final assembly sequence; it does not depict real-time inference, physical simulation or the rollback operation.
- This is the exact run used for the Mac rollback-on panel of Figure 6. The older `gurobi-table-s42-full` saved example has the same brick layout but is a different timed run.

## Figure 6

- File: [figure6-force-colours.png](figure6-force-colours.png)
- All four layouts use the table prompt above, seed 42, and a common orthographic camera and axis limits.
- Colour criterion: maximum stability-score voxel within each brick. Red means score >= 1; green means score < 1.

| Panel | Layout source | Bricks | Red bricks | Static verdict |
|---|---|---:|---:|---|
| (a) RTX / HiGHS, rollback on | `table_featuring_a_flat_recta_s42_full` | 68 | 0 | PASS |
| (b) Mac / Gurobi, rollback on | `live-20261027-075703-106000` | 113 | 0 | PASS |
| (c) RTX / HiGHS, rollback off | `table_featuring_a_flat_recta_s42_no_rollback` | 115 | 5 | FAIL |
| (d) Mac / Gurobi, rollback off | `live-20261027-175029-979000` | 174 | 17 | FAIL |

Mac colours use the original saved per-brick Gurobi scores. RTX colours were computed
by reanalysing the saved RTX layouts on the Mac with the teammate's HiGHS backend;
they are not a new RTX generation or a new hardware timing. The global verdicts
match the original saved metrics. Layouts and generator outputs were not edited.

RTX layouts and the HiGHS implementation come from our teammate's
[brickgpt-demo](https://github.com/sauramt/brickgpt-demo), commit
`90d6efee0183b2360950340e3c82f83b4f6056e1`, under its MIT licence.
Static-force passing does not certify dynamic impact or fracture behaviour.
