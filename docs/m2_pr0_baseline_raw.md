# StateForge M2 PR-0 Baseline Raw Data

## Revision

```text
branch: feature/m2-constraint-guidance
code_commit: 8d74b02b35ccdba5d12bf844d05c3b743c1c4841
generated_at: 2026-10-22T22:38:49.605418+08:00
target_basic_block: m1_target.py::target_block::9-9::entry::1
target_source_hash: f2715dc5cb911fb68c00d4c3229e1f3c2c454e299ccb4aa14c394c6260f0ad6d
max_executions: 20000
random_seeds: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
```

## Environment

```text
python: 3.13.5 | packaged by Anaconda, Inc. | (main, Jun 12 2025, 16:09:02) [GCC 11.2.0]
python_executable: /tmp/sf-m1.1-venv/bin/python
platform: Linux-6.8.0-147-generic-x86_64-with-glibc2.39

$ pip freeze
iniconfig==2.3.1
packaging==26.3
pluggy==1.7.0
pytest==8.3.4
PyYAML==6.0.2
```

## Initial Corpus

```json
{
  "sha256": [
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "d0d2c6a1070df8af6c62c0989d1008c353b755f5cba11b7f9b2cbdf5296cf014",
    "652528305021c6ac0a8ceaece36b520c97503f956a8e01cfd0e0904e29423ab7"
  ],
  "hex": [
    "",
    "413030",
    "414230"
  ]
}
```

## Configurations

```json
{
  "A": {
    "policy": {
      "selection_policy": "uniform",
      "energy_policy": "fixed",
      "fixed_energy": 1
    },
    "max_executions": 20000,
    "max_input_size": 4096,
    "max_corpus_size": 1000,
    "epsilon": 0.2,
    "min_energy": 1,
    "max_energy": 32,
    "fault_policy": "continue"
  },
  "B": {
    "policy": {
      "selection_policy": "distance",
      "energy_policy": "fixed",
      "fixed_energy": 1
    },
    "max_executions": 20000,
    "max_input_size": 4096,
    "max_corpus_size": 1000,
    "epsilon": 0.2,
    "min_energy": 1,
    "max_energy": 32,
    "fault_policy": "continue"
  },
  "C": {
    "policy": {
      "selection_policy": "distance",
      "energy_policy": "distance",
      "fixed_energy": 1
    },
    "max_executions": 20000,
    "max_input_size": 4096,
    "max_corpus_size": 1000,
    "epsilon": 0.2,
    "min_energy": 1,
    "max_energy": 32,
    "fault_policy": "continue"
  }
}
```

## Aggregate Results

```json
{
  "A": {
    "trials": 20,
    "successes": 20,
    "failures": 0,
    "success_rate": 1.0,
    "median_executions_to_target": 3872.0,
    "mean_executions_to_target": 5630.1,
    "min_executions_to_target": 551,
    "max_executions_to_target": 17387,
    "median_wall_clock_to_target_seconds": 0.609338617476169,
    "mean_wall_clock_to_target_seconds": 0.933940537046874,
    "median_elapsed_seconds": 0.6093452074564993,
    "mean_executions_per_second": 6127.069137948485
  },
  "B": {
    "trials": 20,
    "successes": 20,
    "failures": 0,
    "success_rate": 1.0,
    "median_executions_to_target": 2333.0,
    "mean_executions_to_target": 2670.35,
    "min_executions_to_target": 256,
    "max_executions_to_target": 9211,
    "median_wall_clock_to_target_seconds": 0.38021890656091273,
    "mean_wall_clock_to_target_seconds": 0.46565403710119424,
    "median_elapsed_seconds": 0.38022373151034117,
    "mean_executions_per_second": 5939.171851078019
  },
  "C": {
    "trials": 20,
    "successes": 20,
    "failures": 0,
    "success_rate": 1.0,
    "median_executions_to_target": 1608.0,
    "mean_executions_to_target": 2159.65,
    "min_executions_to_target": 97,
    "max_executions_to_target": 4964,
    "median_wall_clock_to_target_seconds": 0.2751239314675331,
    "mean_wall_clock_to_target_seconds": 0.3809396398894023,
    "median_elapsed_seconds": 0.2751374859944917,
    "mean_executions_per_second": 5704.715996101588
  }
}
```

## Per-Run Results

### Group A

```text
trial reached executions exec_to_target wall_to_target best_distance blocks edges retained corpus_size unexpected mapping_failures termination
0 1 3185 3185 0.538377 0 26 29 5 5 0 0 target_reached
1 1 8306 8306 1.324697 0 26 29 5 5 0 0 target_reached
2 1 2116 2116 0.361676 0 26 29 5 5 0 0 target_reached
3 1 551 551 0.086305 0 26 29 5 5 0 0 target_reached
4 1 12001 12001 1.929238 0 26 29 5 5 0 0 target_reached
5 1 1247 1247 0.213029 0 26 29 5 5 0 0 target_reached
6 1 3636 3636 0.577626 0 26 29 5 5 0 0 target_reached
7 1 7968 7968 1.291883 0 26 29 5 5 0 0 target_reached
8 1 2167 2167 0.333011 0 26 29 5 5 0 0 target_reached
9 1 2258 2258 0.347238 0 26 29 5 5 0 0 target_reached
10 1 4108 4108 0.641051 0 26 29 5 5 0 0 target_reached
11 1 1110 1110 0.171456 0 26 29 5 5 0 0 target_reached
12 1 1830 1830 0.293521 0 26 29 5 5 0 0 target_reached
13 1 6642 6642 1.037574 0 26 29 5 5 0 0 target_reached
14 1 11269 11269 1.945526 0 26 29 5 5 0 0 target_reached
15 1 5699 5699 0.939526 0 26 29 5 5 0 0 target_reached
16 1 7440 7440 1.202291 0 26 29 5 5 0 0 target_reached
17 1 10653 10653 1.793257 0 26 29 5 5 0 0 target_reached
18 1 3029 3029 0.555301 0 26 29 5 5 0 0 target_reached
19 1 17387 17387 3.096227 0 26 29 5 5 0 0 target_reached
```

### Group B

```text
trial reached executions exec_to_target wall_to_target best_distance blocks edges retained corpus_size unexpected mapping_failures termination
0 1 2617 2617 0.442089 0 26 29 5 5 0 0 target_reached
1 1 4173 4173 0.768018 0 26 29 5 5 0 0 target_reached
2 1 1229 1229 0.234533 0 26 29 5 5 0 0 target_reached
3 1 2049 2049 0.360326 0 26 29 5 5 0 0 target_reached
4 1 2732 2732 0.499925 0 26 29 5 5 0 0 target_reached
5 1 1089 1089 0.200402 0 26 29 5 5 0 0 target_reached
6 1 1100 1100 0.199210 0 26 29 5 5 0 0 target_reached
7 1 6522 6522 1.159179 0 26 29 5 5 0 0 target_reached
8 1 3361 3361 0.550537 0 26 29 5 5 0 0 target_reached
9 1 256 256 0.036140 0 26 29 5 5 0 0 target_reached
10 1 1322 1322 0.231536 0 26 29 5 5 0 0 target_reached
11 1 1113 1113 0.160082 0 26 29 5 5 0 0 target_reached
12 1 2715 2715 0.400112 0 26 29 5 5 0 0 target_reached
13 1 479 479 0.065686 0 26 29 5 5 0 0 target_reached
14 1 857 857 0.135404 0 26 29 5 5 0 0 target_reached
15 1 3204 3204 0.561294 0 26 29 5 5 0 0 target_reached
16 1 5028 5028 0.874112 0 26 29 5 5 0 0 target_reached
17 1 9211 9211 1.656714 0 26 29 5 5 0 0 target_reached
18 1 1526 1526 0.273284 0 26 29 5 5 0 0 target_reached
19 1 2824 2824 0.504498 0 26 29 5 5 0 0 target_reached
```

### Group C

```text
trial reached executions exec_to_target wall_to_target best_distance blocks edges retained corpus_size unexpected mapping_failures termination
0 1 2627 2627 0.477493 0 26 29 5 5 0 0 target_reached
1 1 4194 4194 0.731275 0 26 29 5 5 0 0 target_reached
2 1 97 97 0.014753 0 26 29 5 5 0 0 target_reached
3 1 550 550 0.086735 0 26 29 5 5 0 0 target_reached
4 1 2139 2139 0.381872 0 26 29 5 5 0 0 target_reached
5 1 1305 1305 0.242940 0 26 29 5 5 0 0 target_reached
6 1 4165 4165 0.732224 0 26 29 5 5 0 0 target_reached
7 1 1068 1068 0.200367 0 26 29 5 5 0 0 target_reached
8 1 3302 3302 0.588212 0 26 29 5 5 0 0 target_reached
9 1 1674 1674 0.268900 0 26 29 5 5 0 0 target_reached
10 1 174 174 0.026818 0 26 29 5 5 0 0 target_reached
11 1 1146 1146 0.229569 0 26 29 5 5 0 0 target_reached
12 1 1322 1322 0.272428 0 26 29 5 5 0 0 target_reached
13 1 4240 4240 0.746437 0 26 29 5 5 0 0 target_reached
14 1 4964 4964 0.780535 0 26 29 5 5 0 0 target_reached
15 1 197 197 0.036990 0 26 29 5 5 0 0 target_reached
16 1 4502 4502 0.803070 0 26 29 5 5 0 0 target_reached
17 1 2657 2657 0.495127 0 26 29 5 5 0 0 target_reached
18 1 1542 1542 0.277820 0 26 29 5 5 0 0 target_reached
19 1 1328 1328 0.225227 0 26 29 5 5 0 0 target_reached
```

## Test Suite

```text
$ /tmp/sf-m1.1-venv/bin/python -m pytest -q
........................................................................ [ 72%]
...........................                                              [100%]
99 passed in 0.56s
```

## Reproduction

```text
$ cd /home/landasika/icassp/stateforge-clean
$ /tmp/sf-m1.1-venv/bin/python evaluation/scripts/m1_pr0_baseline.py
$ cat evaluation/baselines/m1_pr0.json
```
