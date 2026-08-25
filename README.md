# DissMsc

Artifact release for an MSc dissertation studying **how LLM agent teams collaborate**: parallelism, information blockage, complementary access, and verification authority, on software-engineering tasks. The benchmark extends TeamBench-style tasks onto a leader–member dynamic-team stack built on the **jiuwenswarm** multi-agent framework, and releases the complete experimental corpus: **186 team runs across 19 batches** (scenarios S1–S5, two persona arms, two enforcement conditions), plus the code, task bundles, framework patches, and analysis metrics needed to reproduce and re-analyse them.

All runs use `deepseek-v4-pro` as the underlying model. The team leader composes its own roster per task (dynamic roster, up to 10 members drawn from a 9-node worker pool plus leader).

## Repository layout

| Folder | Contents |
|---|---|
| [`run_archives/`](run_archives/) | The primary data: 186 self-contained run trace archives in 19 batch directories (see grid below). |
| [`run_code/`](run_code/) | The minimal run rig: provisioning, environment, persona configs, ACL/task staging, scenario hooks (S3/S4/S5), kickoff prompt, single-run launch chain, batch runners, and regrade scripts. |
| [`task_sets/`](task_sets/) | The exact task bundles run: `core12/` (12 core-grid tasks), `stress8/` (8 stress tasks, S1B), `s2_bundles/` (10 composed pair bundles P1–P10 + per-subtask graders), `evals/` (the 20 eval bundles with `grade.sh` ground truth). |
| [`jiuwenswarm_framework_mods/`](jiuwenswarm_framework_mods/) | Our modifications to the framework: current versions of every changed file at their repo-relative paths. Upstream base: `openJiuwen-ai/jiuwenswarm`, branch `develop`, commit `80e25b36`; our branch is mirrored at [`CChriz/jiuwenswarm-611`](https://github.com/CChriz/jiuwenswarm-611). |
| [`metrics/`](metrics/) | Analysis code. `Metrics/` the metric-suite modules (run index, generic member/role metrics, codebook, per-scenario analyses S2–S5, authority, domination, recruitment, repetition, teamwidth, conformance, exemplar library) plus rendered figures. `Trajectory metrics/` the trajectory layer (raw-stream parsing, run walks, trajectory automata, canonical strips, funnels). |

## Experimental design

**Scenarios** (each probes one collaboration axis):

| Scenario | Axis | Design |
|---|---|---|
| **S1A** | Baseline, solo-sufficient | 12 core tasks a single agent could complete; measures what teaming adds/costs. |
| **S1B** | Baseline, solo-insufficient | 8 stress tasks beyond a single agent's comfortable scope. |
| **S2** | Parallelism | 10 composed pair bundles (two independent tasks in one flat workspace); measures overlap, speedup, and cost of parallel execution. |
| **S3** | Information blockage | Mid-run communication blocks, in two doses: **full** (all routes to a phase blocked) and **partial** (a survivor route remains); measures rerouting and recovery. |
| **S4** | Complementary access | Workspace write-partition between executors (closed dose): each executor can only write its half; measures coordination across the seam. |
| **S5** | Verification sensitivity | Spec-knowledge split between planner and verifier, in two regimes: **partial** (planner holds ~half the spec) and **minimal** (near-full spec minus one graded unit); measures whether the verification funnel catches what it cannot see. |

**Arms** (persona conditions):

- **Arm 1 — base**: stock role personas (planner / executor / verifier style roles).
- **Arm 2 — specialist**: task-specialised personas, with the team roster injected into member context and escalation rewritten to peer-ask. Note arm 2 bundles these three changes together; the only single-variable persona contrast is the S1A prompt-only pair.

**Enforcement conditions**:

- **Prompt-only**: role/access rules stated in prompts only; leader runs as a normal user.
- **Enforced**: OS-level ACLs back the rules; a tamper-proof `jw_leader` account (non-owner, no sudo) runs the leader.

## The run grid (`run_archives/`)

| Scenario | Arm 1 (base) | n | Arm 2 (specialist) | n |
|---|---|---|---|---|
| S1A solo-sufficient | `S1A_team_dyn_pro` (prompt-only) + `S1A_team_enf_pro` (enforced) | 12 + 12 | `S1A_team_dyn_pro_arm2`           | 12 |
| S1B solo-insufficient | `S1B_team_dyn_pro` (prompt-only) + `S1B_team_enf_pro` (enforced) | 8 + 8 | `S1B_team_enf_pro_arm2`  | 8 |
| S2 parallel pairs | `S2_pairs_pro` (prompt-only) + `S2_pairs_enf_pro` (enforced) | 10 + 10 | `S2_pairs_enf_pro_arm2`  | 10 |
| S3 full blockage | `S3_full_enf_pro` | 12 | `S3_full_enf_pro_arm2` | 12 |
| S3 partial blockage | `S3_partial_enf_pro` | 12 | `S3_partial_enf_pro_arm2` | 12 |
| S4 complementary access | `S4_enf_pro` | 12 | `S4_enf_pro_arm2` | 12 |
| S5 verification sensitivity | `S5_partial_enf_pro` (6) + `S5_minimal_enf_pro` (6) | 12 | `S5_partial_enf_pro_arm2` (6) + `S5_minimal_enf_pro_arm2` (6) | 12 |

Totals: arm 1 = 108 runs, arm 2 = 78 runs → **186**. All S3–S5 batches are enforced. Directory naming: `pro` = the deepseek-v4-pro model tier, `dyn` = prompt-only dynamic-roster leader, `enf` = enforced ACLs, `_arm2` = specialist arm.

### Anatomy of one run archive

Each run is a self-contained directory `run_archives/<batch>/<task>_<label>/`:

```
<task>_<label>/
├── traces/
│   ├── nodes/nodeK/stream-node-*-full.jsonl   # raw per-member token streams (source of truth)
│   ├── leader/stream-node-*-full.jsonl        # leader stream
│   └── team_logs/                             # per-node framework logs
├── members/                                   # the same streams, renamed by persona/role
├── messages.json                              # inter-member messages (order 0 = the leader's kickoff broadcast)
├── crossings.json, timeline.json, turns_by_member.json   # derived cross-checks
├── manifest.json, MANIFEST.txt                # archive manifest + per-stream sha256
└── run_current/
    ├── workspace/                             # the graded deliverable
    ├── attestation.json                       # the team's self-reported verdict (do NOT trust for scoring)
    ├── spec/, brief.md, reports/              # task inputs and reports
```

Each **batch** directory also carries `batch_results.tsv` (one row per run: outcome + original archive path) and `scenario1_regrade.tsv` / `scenario1_regrade_records.json` (ground-truth regrades via `grade.sh`).

Notes on the archives:

- The trace streams capture model *output* (reasoning/action tokens and events), not the injected system prompts. The persona definitions and kickoff prompt live in `run_code/personas/` and `run_code/kickoffs/`.
- **Scoring**: always use the `grade.sh` ground truth (regrade scripts in `run_code/grading/`), never `attestation.json` — team self-attestations are unreliable by design and part of what the benchmark measures.

## Reproducing

1. **Framework**: clone `openJiuwen-ai/jiuwenswarm` at `80e25b36`, apply the files in `jiuwenswarm_framework_mods/modified_files/` (or use the mirror branch at `CChriz/jiuwenswarm-611`).
2. **Rig**: provision the node pool and `jw_leader` account, set your own `API_KEY` in `run_code/env/team.env`, install personas.
3. **Run**: pick a batch driver from `run_code/runners/` (e.g. `run_s3_blockage.sh full`); each stages a bundle from `task_sets/`, applies the scenario hook from `run_code/conditions/`, launches the team, and archives the run.
4. **Grade**: `run_code/grading/regrade_scenario1.py <batch_root> <label>` against `task_sets/evals/`.
5. **Analyse**: modules in `metrics/` rebuild the run index and metric outputs from the raw streams in `run_archives/`.

