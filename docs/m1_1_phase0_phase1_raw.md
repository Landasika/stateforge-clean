# StateForge M1.1 Phase 0-1 Raw Data

## Repository

```text
remote origin: git@github.com:Landasika/stateforge-clean.git
branch: main
baseline commit: 8960bf7d249423d8606cc4b50cc95afb41ea333c
baseline commit date: 2026-10-21 23:36:45 +0800
baseline commit subject: implement M1 basic-block directed greybox fuzzing
```

```text
$ git fetch origin
From github.com:Landasika/stateforge-clean
 * branch            main       -> FETCH_HEAD

$ git pull --ff-only origin main
Already up to date.

$ git rev-parse HEAD
8960bf7d249423d8606cc4b50cc95afb41ea333c

$ git log --oneline -3
8960bf7 implement M1 basic-block directed greybox fuzzing
bca6186 remove vendored targets: engine only
c34edb1 init: stateforge code (comments/docs/tests/history stripped)
```

```text
$ git ls-files cli.py fuzzing/guidance/campaign.py fuzzing/feedback/corpus.py fuzzing/guidance/scheduler.py runtime/tracer.py tests/test_guidance_campaign.py
cli.py
fuzzing/feedback/corpus.py
fuzzing/guidance/campaign.py
fuzzing/guidance/scheduler.py
runtime/tracer.py
tests/test_guidance_campaign.py
```

## Environment

```text
$ python -m venv /tmp/sf-m1.1-venv
$ /tmp/sf-m1.1-venv/bin/python -VV
Python 3.13.5 | packaged by Anaconda, Inc. | (main, Jun 12 2025, 16:09:02) [GCC 11.2.0]

$ /tmp/sf-m1.1-venv/bin/pip freeze
iniconfig==2.3.1
packaging==26.3
pluggy==1.7.0
pytest==8.3.4
PyYAML==6.0.2

$ uname -a
Linux landasika 6.8.0-147-generic #147-Ubuntu SMP PREEMPT_DYNAMIC Thu Sep 24 11:33:16 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux

CPU: QEMU Virtual CPU version 2.5+
Mem total: 15Gi
```

## Phase 0 Baseline Test

```text
$ cd /home/landasika/icassp/stateforge-clean
$ /tmp/sf-m1.1-venv/bin/python -m pytest -q
........................................................................ [ 96%]
...                                                                      [100%]
75 passed in 0.37s
EXIT=0
```

```text
$ git status --short
<no output>
```

## Phase 1 Working Tree

```text
$ git status --short
 M fuzzing/feedback/corpus.py
 M fuzzing/guidance/campaign.py
 M fuzzing/guidance/results.py
 M runtime/tracer.py
 M tests/test_guidance_campaign.py
 M tests/test_guidance_corpus.py
 M tests/test_guidance_tracer.py
?? docs/
?? tests/test_guidance_mapping.py
```

```text
$ git diff --stat
 fuzzing/feedback/corpus.py      | 85 ++++++++++++++++++++++++++++++-----------
 fuzzing/guidance/campaign.py    |  8 ++++
 fuzzing/guidance/results.py     | 15 ++++++++
 runtime/tracer.py               | 16 +++---
 tests/test_guidance_campaign.py | 75 ++++++++++++++++++++++++++++++++++--
 tests/test_guidance_corpus.py   | 74 +++++++++++++++++++++++++++++++++++
 tests/test_guidance_tracer.py   | 48 +++++++++++++++++++++++++++++++
 7 files changed, 291 insertions(+), 30 deletions(-)
```

```text
$ wc -l tests/test_guidance_mapping.py
123 tests/test_guidance_mapping.py
```

## Corpus Capacity Raw Observations

```json
[
  {
    "max_size": 1,
    "target_candidates": 25,
    "active_len": 1,
    "archive_len": 24,
    "max_observed_active_len": 1,
    "best_distance": 0,
    "active_inputs_hex": [
      "12"
    ],
    "archived_inputs_hex": [
      "01",
      "00",
      "03",
      "02",
      "04",
      "06",
      "07",
      "08",
      "09",
      "0a",
      "05",
      "0b",
      "0d",
      "0e",
      "0f",
      "10",
      "11",
      "0c",
      "13",
      "14",
      "15",
      "16",
      "17",
      "18"
    ],
    "active_union_blocks": 2,
    "active_union_edges": 1
  },
  {
    "max_size": 10,
    "target_candidates": 25,
    "active_len": 10,
    "archive_len": 15,
    "max_observed_active_len": 10,
    "best_distance": 0,
    "active_inputs_hex": [
      "02",
      "04",
      "05",
      "07",
      "08",
      "0b",
      "0c",
      "0f",
      "10",
      "12"
    ],
    "archived_inputs_hex": [
      "0a",
      "03",
      "09",
      "01",
      "0e",
      "06",
      "00",
      "11",
      "0d",
      "13",
      "14",
      "15",
      "16",
      "17",
      "18"
    ],
    "active_union_blocks": 13,
    "active_union_edges": 10
  },
  {
    "max_size": 1,
    "target_candidates": 0,
    "active_len": 1,
    "archive_len": 0,
    "best_distance": 7,
    "active_inputs_hex": [
      "62657374"
    ]
  }
]
```

Corpus capacity regression commands:

```text
$ /tmp/sf-m1.1-venv/bin/python -m pytest -q tests/test_guidance_corpus.py
17 passed in 0.06s
EXIT=0
```

Archived target persistence raw observations:

```json
{
  "executions": 3,
  "target_reached": true,
  "archived_targets": 1,
  "active_len": 2,
  "active_inputs_hex": [
    "414243",
    "41424330"
  ],
  "archived_inputs_hex": [
    "4142433030"
  ],
  "target_archive_files": [
    "/tmp/m1_1_archive_raw/target_archive/seed_2e031db6317ef44c.bin"
  ],
  "target_archive_file_bytes_hex": [
    "4142433030"
  ]
}
```

## Trace Isolation Raw Observations

```json
{
  "successful_and_invalid_inputs": {
    "executions": 500,
    "max_session_events_observed": 0,
    "final_session_events": 0,
    "final_request_index_entries": 0,
    "total_trace_events": 3750
  },
  "exception_inputs": {
    "executions": 200,
    "max_session_events_observed": 0,
    "final_session_events": 0,
    "final_request_index_entries": 0,
    "unexpected_exceptions": 200
  },
  "unresolved_mapping": {
    "trace_events": 6,
    "unresolved_events": 6,
    "campaign_mapping_failures": 6,
    "covered_blocks": 0,
    "distance": null,
    "target_reached": false,
    "final_session_events": 0
  }
}
```

```text
$ /tmp/sf-m1.1-venv/bin/python -m pytest -q tests/test_guidance_tracer.py
10 passed in 0.06s
EXIT=0
```

## Mapping and Replay Raw Observations

```text
$ /tmp/sf-m1.1-venv/bin/python -m pytest -q tests/test_guidance_mapping.py
4 passed in 0.05s
EXIT=0
```

```json
{
  "summary": {
    "target_basic_block": "m1_target.py::target_block::9-9::entry::1",
    "target_reached": true,
    "executions": 100,
    "executions_to_target": 100,
    "wall_clock_time_to_target_seconds": 0.044582091039046645,
    "best_distance": 0,
    "unique_covered_blocks": 26,
    "unique_valid_icfg_edges": 29,
    "retained_seeds": 5,
    "unexpected_exceptions": 0,
    "mapping_failures": 0,
    "mapping_failure_rate": 0.0,
    "termination_reason": "target_reached",
    "elapsed_seconds": 0.04482576495502144,
    "target_reaching_input_id": "candidate_100",
    "output_dir": "/tmp/m1_1_phase1_replay",
    "archived_target_seeds": 0
  },
  "target_reaching_input_hex": "414243",
  "replay_target_reached": true,
  "replay_distance": 0,
  "replay_error": null,
  "replay_trace_events": 18,
  "replay_unresolved_events": 0,
  "replay_covered_blocks": 24,
  "target_block_present_in_replay": true,
  "session_events_after_replay": 0
}
```

## Post-Change Test Runs

```text
$ /tmp/sf-m1.1-venv/bin/python -m pytest -q tests/test_guidance_corpus.py tests/test_guidance_tracer.py tests/test_guidance_mapping.py tests/test_guidance_campaign.py
.................................................                        [100%]
49 passed in 0.22s
EXIT=0
```

```text
$ /tmp/sf-m1.1-venv/bin/python -m pytest -q
........................................................................ [ 78%]
....................                                                     [100%]
92 passed in 0.52s
EXIT=0
```
