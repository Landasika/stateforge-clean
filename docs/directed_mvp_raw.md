# StateForge Directed Greybox MVP Raw Data

## Revision and Environment

```text
branch: feature/directed-greybox-mvp
code_commit: 9dcade4742c85ec051791a006e73eb2cfe30b5af
generated_at: 2026-10-23T15:14:32.798136+08:00
trials: 20
max_executions: 2000
energy: 1
python: 3.13.5 | packaged by Anaconda, Inc. | (main, Jun 12 2025, 16:09:02) [GCC 11.2.0]
python_executable: /tmp/sf-m1.1-venv/bin/python
platform: Linux-6.8.0-147-generic-x86_64-with-glibc2.39
```

## Targets

```json
{
  "toy_simple": {
    "target_basic_block": "app.py::deep_target::9-9::terminal::1",
    "target_source_hash": "dacf5c6023efd022d71223909b7bedcd94d9d53b4d60c6245132bca38330b691",
    "initial_corpus_hex": [
      "0000",
      "3200"
    ],
    "initial_corpus_sha256": [
      "96a296d224f285c67bee93c30f8a309157f0daa35dc5b87e410b78630a09cfc7",
      "913da1f8df6f8fd47593840d533ba0458cc9873996bf310460abb495b34c232a"
    ]
  },
  "toy_interprocedural": {
    "target_basic_block": "app.py::gate::9-9::terminal::1",
    "target_source_hash": "d6caea8c6804aff963330d894b43e79a80b18b4a12bf4937f02047d501c761cc",
    "initial_corpus_hex": [
      "00000000"
    ],
    "initial_corpus_sha256": [
      "df3f619804a92fdb4057192dc43dd748ea778adc52bc498ce80524c014b81119"
    ]
  }
}
```

## Aggregate Results

```json
{
  "toy_simple": {
    "directed": {
      "trials": 20,
      "successes": 20,
      "censored": 0,
      "success_rate": 1.0,
      "mean_executions_to_target": 7.1,
      "median_executions_to_target": 6.0,
      "min_executions_to_target": 3,
      "max_executions_to_target": 17,
      "median_wall_clock_to_target_seconds": 0.011998588510323316,
      "mean_executions_per_second": 508.47510598632067,
      "mean_covered_blocks": 14,
      "mean_valid_icfg_edges": 15
    },
    "uniform": {
      "trials": 20,
      "successes": 20,
      "censored": 0,
      "success_rate": 1.0,
      "mean_executions_to_target": 8.3,
      "median_executions_to_target": 7.5,
      "min_executions_to_target": 3,
      "max_executions_to_target": 21,
      "median_wall_clock_to_target_seconds": 0.011597543489187956,
      "mean_executions_per_second": 585.1580090141179,
      "mean_covered_blocks": 14,
      "mean_valid_icfg_edges": 15
    },
    "coverage_only": {
      "trials": 20,
      "successes": 20,
      "censored": 0,
      "success_rate": 1.0,
      "mean_executions_to_target": 8.3,
      "median_executions_to_target": 7.5,
      "min_executions_to_target": 3,
      "max_executions_to_target": 21,
      "median_wall_clock_to_target_seconds": 0.010419198486488312,
      "mean_executions_per_second": 730.599503477305,
      "mean_covered_blocks": 14,
      "mean_valid_icfg_edges": 15
    }
  },
  "toy_interprocedural": {
    "directed": {
      "trials": 20,
      "successes": 20,
      "censored": 0,
      "success_rate": 1.0,
      "mean_executions_to_target": 78.25,
      "median_executions_to_target": 72.0,
      "min_executions_to_target": 13,
      "max_executions_to_target": 176,
      "median_wall_clock_to_target_seconds": 0.09185508149676025,
      "mean_executions_per_second": 753.6614549159351,
      "mean_covered_blocks": 20,
      "mean_valid_icfg_edges": 22.8
    },
    "uniform": {
      "trials": 20,
      "successes": 20,
      "censored": 0,
      "success_rate": 1.0,
      "mean_executions_to_target": 113.25,
      "median_executions_to_target": 105.5,
      "min_executions_to_target": 24,
      "max_executions_to_target": 253,
      "median_wall_clock_to_target_seconds": 0.13722427800530568,
      "mean_executions_per_second": 748.1711919166042,
      "mean_covered_blocks": 20,
      "mean_valid_icfg_edges": 23
    },
    "coverage_only": {
      "trials": 20,
      "successes": 20,
      "censored": 0,
      "success_rate": 1.0,
      "mean_executions_to_target": 113.25,
      "median_executions_to_target": 105.5,
      "min_executions_to_target": 24,
      "max_executions_to_target": 253,
      "median_wall_clock_to_target_seconds": 0.14802814251743257,
      "mean_executions_per_second": 734.8451669883576,
      "mean_covered_blocks": 20,
      "mean_valid_icfg_edges": 23
    }
  }
}
```

## Per-Run Executions-to-Target

```text
target arm trial executions_to_target best_distance target_reached termination_reason
toy_simple directed 0 7 0 True target_reached
toy_simple directed 1 4 0 True target_reached
toy_simple directed 2 11 0 True target_reached
toy_simple directed 3 4 0 True target_reached
toy_simple directed 4 17 0 True target_reached
toy_simple directed 5 3 0 True target_reached
toy_simple directed 6 9 0 True target_reached
toy_simple directed 7 11 0 True target_reached
toy_simple directed 8 3 0 True target_reached
toy_simple directed 9 7 0 True target_reached
toy_simple directed 10 3 0 True target_reached
toy_simple directed 11 5 0 True target_reached
toy_simple directed 12 6 0 True target_reached
toy_simple directed 13 12 0 True target_reached
toy_simple directed 14 14 0 True target_reached
toy_simple directed 15 6 0 True target_reached
toy_simple directed 16 3 0 True target_reached
toy_simple directed 17 3 0 True target_reached
toy_simple directed 18 9 0 True target_reached
toy_simple directed 19 5 0 True target_reached
toy_simple uniform 0 4 0 True target_reached
toy_simple uniform 1 8 0 True target_reached
toy_simple uniform 2 8 0 True target_reached
toy_simple uniform 3 5 0 True target_reached
toy_simple uniform 4 17 0 True target_reached
toy_simple uniform 5 3 0 True target_reached
toy_simple uniform 6 9 0 True target_reached
toy_simple uniform 7 9 0 True target_reached
toy_simple uniform 8 21 0 True target_reached
toy_simple uniform 9 7 0 True target_reached
toy_simple uniform 10 3 0 True target_reached
toy_simple uniform 11 5 0 True target_reached
toy_simple uniform 12 10 0 True target_reached
toy_simple uniform 13 13 0 True target_reached
toy_simple uniform 14 17 0 True target_reached
toy_simple uniform 15 6 0 True target_reached
toy_simple uniform 16 3 0 True target_reached
toy_simple uniform 17 3 0 True target_reached
toy_simple uniform 18 9 0 True target_reached
toy_simple uniform 19 6 0 True target_reached
toy_simple coverage_only 0 4 0 True target_reached
toy_simple coverage_only 1 8 0 True target_reached
toy_simple coverage_only 2 8 0 True target_reached
toy_simple coverage_only 3 5 0 True target_reached
toy_simple coverage_only 4 17 0 True target_reached
toy_simple coverage_only 5 3 0 True target_reached
toy_simple coverage_only 6 9 0 True target_reached
toy_simple coverage_only 7 9 0 True target_reached
toy_simple coverage_only 8 21 0 True target_reached
toy_simple coverage_only 9 7 0 True target_reached
toy_simple coverage_only 10 3 0 True target_reached
toy_simple coverage_only 11 5 0 True target_reached
toy_simple coverage_only 12 10 0 True target_reached
toy_simple coverage_only 13 13 0 True target_reached
toy_simple coverage_only 14 17 0 True target_reached
toy_simple coverage_only 15 6 0 True target_reached
toy_simple coverage_only 16 3 0 True target_reached
toy_simple coverage_only 17 3 0 True target_reached
toy_simple coverage_only 18 9 0 True target_reached
toy_simple coverage_only 19 6 0 True target_reached
toy_interprocedural directed 0 176 0 True target_reached
toy_interprocedural directed 1 13 0 True target_reached
toy_interprocedural directed 2 69 0 True target_reached
toy_interprocedural directed 3 81 0 True target_reached
toy_interprocedural directed 4 104 0 True target_reached
toy_interprocedural directed 5 35 0 True target_reached
toy_interprocedural directed 6 16 0 True target_reached
toy_interprocedural directed 7 135 0 True target_reached
toy_interprocedural directed 8 74 0 True target_reached
toy_interprocedural directed 9 101 0 True target_reached
toy_interprocedural directed 10 22 0 True target_reached
toy_interprocedural directed 11 87 0 True target_reached
toy_interprocedural directed 12 69 0 True target_reached
toy_interprocedural directed 13 119 0 True target_reached
toy_interprocedural directed 14 53 0 True target_reached
toy_interprocedural directed 15 172 0 True target_reached
toy_interprocedural directed 16 54 0 True target_reached
toy_interprocedural directed 17 76 0 True target_reached
toy_interprocedural directed 18 39 0 True target_reached
toy_interprocedural directed 19 70 0 True target_reached
toy_interprocedural uniform 0 91 0 True target_reached
toy_interprocedural uniform 1 30 0 True target_reached
toy_interprocedural uniform 2 133 0 True target_reached
toy_interprocedural uniform 3 50 0 True target_reached
toy_interprocedural uniform 4 109 0 True target_reached
toy_interprocedural uniform 5 154 0 True target_reached
toy_interprocedural uniform 6 113 0 True target_reached
toy_interprocedural uniform 7 253 0 True target_reached
toy_interprocedural uniform 8 180 0 True target_reached
toy_interprocedural uniform 9 118 0 True target_reached
toy_interprocedural uniform 10 24 0 True target_reached
toy_interprocedural uniform 11 194 0 True target_reached
toy_interprocedural uniform 12 64 0 True target_reached
toy_interprocedural uniform 13 70 0 True target_reached
toy_interprocedural uniform 14 52 0 True target_reached
toy_interprocedural uniform 15 241 0 True target_reached
toy_interprocedural uniform 16 130 0 True target_reached
toy_interprocedural uniform 17 98 0 True target_reached
toy_interprocedural uniform 18 102 0 True target_reached
toy_interprocedural uniform 19 59 0 True target_reached
toy_interprocedural coverage_only 0 91 0 True target_reached
toy_interprocedural coverage_only 1 30 0 True target_reached
toy_interprocedural coverage_only 2 133 0 True target_reached
toy_interprocedural coverage_only 3 50 0 True target_reached
toy_interprocedural coverage_only 4 109 0 True target_reached
toy_interprocedural coverage_only 5 154 0 True target_reached
toy_interprocedural coverage_only 6 113 0 True target_reached
toy_interprocedural coverage_only 7 253 0 True target_reached
toy_interprocedural coverage_only 8 180 0 True target_reached
toy_interprocedural coverage_only 9 118 0 True target_reached
toy_interprocedural coverage_only 10 24 0 True target_reached
toy_interprocedural coverage_only 11 194 0 True target_reached
toy_interprocedural coverage_only 12 64 0 True target_reached
toy_interprocedural coverage_only 13 70 0 True target_reached
toy_interprocedural coverage_only 14 52 0 True target_reached
toy_interprocedural coverage_only 15 241 0 True target_reached
toy_interprocedural coverage_only 16 130 0 True target_reached
toy_interprocedural coverage_only 17 98 0 True target_reached
toy_interprocedural coverage_only 18 102 0 True target_reached
toy_interprocedural coverage_only 19 59 0 True target_reached
```

## Demo Campaign

```json
{
  "target_basic_block": "app.py::deep_target::9-9::terminal::1",
  "target_reached": true,
  "executions": 10,
  "executions_to_target": 10,
  "wall_clock_time_to_target_seconds": 0.022190154064446688,
  "best_distance": 0,
  "unique_covered_blocks": 14,
  "unique_valid_icfg_edges": 15,
  "retained_seeds": 3,
  "unexpected_exceptions": 0,
  "mapping_failures": 0,
  "mapping_failure_rate": 0.0,
  "termination_reason": "target_reached",
  "elapsed_seconds": 0.022319877054542303,
  "target_reaching_input_id": "candidate_10",
  "output_dir": "/home/landasika/icassp/stateforge-clean/evaluation/directed_mvp/demo",
  "scheduler": {
    "name": "guided",
    "epsilon": 0.2,
    "random_seed": 42,
    "min_energy": 1,
    "max_energy": 1
  },
  "mutation": {
    "operators": [
      "bit_flip",
      "byte_replace",
      "byte_insert",
      "byte_delete",
      "range_overwrite",
      "splice"
    ],
    "random_seed": 42,
    "max_input_size": 64
  },
  "corpus_size": 3,
  "total_trace_events": 127,
  "source_hash": "dacf5c6023efd022d71223909b7bedcd94d9d53b4d60c6245132bca38330b691",
  "target_input_path": "/home/landasika/icassp/stateforge-clean/evaluation/directed_mvp/demo/target_reaching_input.bin",
  "execution_throughput_per_second": 448.0311417291121,
  "config": {
    "max_executions": 2000,
    "max_seconds": null,
    "max_input_size": 64,
    "max_corpus_size": 1000,
    "epsilon": 0.2,
    "random_seed": 42,
    "stop_on_target": true,
    "fault_policy": "continue",
    "allow_stale_ir": false,
    "output_dir": "/home/landasika/icassp/stateforge-clean/evaluation/directed_mvp/demo",
    "min_energy": 1,
    "max_energy": 1,
    "scheduler": "guided",
    "corpus_policy": "distance",
    "progress_every": 100
  }
}
```

```text
execution candidate_id parent_distance candidate_distance best_distance nearest_block distance_improved mutation_operator target_reached
1 seed_96a296d224f285c6 None 2 2 app.py::deep_target::7-7::branch::1 False None False
2 seed_913da1f8df6f8fd4 None 1 1 app.py::deep_target::8-8::branch::1 False None False
3 candidate_3 2 1 1 app.py::deep_target::8-8::branch::1 True splice False
4 candidate_4 2 2 1 app.py::deep_target::7-7::branch::1 False splice False
5 candidate_5 1 1 1 app.py::deep_target::8-8::branch::1 False byte_replace False
6 candidate_6 2 1 1 app.py::deep_target::8-8::branch::1 True bit_flip False
7 candidate_7 2 2 1 app.py::deep_target::7-7::branch::1 False bit_flip False
8 candidate_8 1 1 1 app.py::deep_target::8-8::branch::1 False byte_replace False
9 candidate_9 2 1 1 app.py::deep_target::8-8::branch::1 True range_overwrite False
10 candidate_10 1 0 0 app.py::deep_target::9-9::terminal::1 True range_overwrite True
```

## Replay

```text
target_reaching_input_hex: 3273
```

## Test Runs

```text
$ /tmp/sf-m1.1-venv/bin/python -m pytest -q
........................................................................ [ 81%]
................                                                         [100%]
88 passed in 0.43s

$ /tmp/sf-m1.1-venv/bin/python -m pytest -q tests/test_directed_mapping.py tests/test_toy_directed_mvp.py
.............                                                            [100%]
13 passed in 0.23s
```

## Reproduction

```text
$ cd /home/landasika/icassp/stateforge-clean
$ /tmp/sf-m1.1-venv/bin/python evaluation/scripts/directed_mvp_baseline.py
$ cat evaluation/directed_mvp/baseline.json
```
