# Temporary-Profile Constants Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make commissioned profile values and executor timing/safety constants self-documenting and single-source while preserving runtime behavior.

**Architecture:** Define ESPHome substitutions at the top of `full_config.yaml`, reference the commissioned substitutions from the six template-number startup values, and remove the redundant commissioned globals. Replace timing and integer-limit literals in executor actions with named substitutions or `INT_MAX`; lifecycle phases remain documented beside their state global.

**Tech Stack:** ESPHome YAML substitutions, embedded C++ lambdas, Python text-contract tests

## Global Constraints

- Keep commissioned values exactly MIN 50/50, NORMAL 60/57, MAX 100/100.
- Use `MAX_SAFE_LEASE_SECONDS: "43200"` with a comment identifying the 12-hour ownership bound.
- Use `temporary_profile_modbus_settle_delay: "200ms"` and `temporary_profile_mode_ack_timeout_ms: "5000"`.
- Replace every executor generation literal `2147483647` with `INT_MAX`.
- Remove the six unused `default_*` globals; substitutions become the only commissioned-value source.
- Do not add optimistic-state readback as hardware verification.
- Preserve lifecycle behavior, API shape, entity IDs, unrelated configuration, and sibling repositories.

---

### Task 1: Add failing constants and documentation contracts

**Files:**
- Modify: `tests/test_full_config_contract.py`

**Interfaces:**
- Consumes: `full_config.yaml` as UTF-8 text
- Produces: regression checks for substitution definitions/references and removal of magic literals/globals

- [ ] Add tests asserting a top-level `substitutions:` section defines all six commissioned profile values, `MAX_SAFE_LEASE_SECONDS: "43200"`, `temporary_profile_modbus_settle_delay: "200ms"`, and `temporary_profile_mode_ack_timeout_ms: "5000"`, with commissioning/12-hour comments.
- [ ] Assert each of the six number entities uses its matching `${...}` commissioned substitution as `initial_value`.
- [ ] Assert no `default_*` commissioned global remains.
- [ ] Assert `${MAX_SAFE_LEASE_SECONDS}` appears in lease validation and timer bounding, while `4294967` is absent.
- [ ] Assert both executor delays use `${temporary_profile_modbus_settle_delay}`, the watcher uses `${temporary_profile_mode_ack_timeout_ms}`, and the raw timing literals are absent from executor logic.
- [ ] Assert executor generation guards use `INT_MAX` and `2147483647` is absent.
- [ ] Run `python -c "import runpy; ns=runpy.run_path('tests/test_full_config_contract.py'); tests=[f for n,f in ns.items() if n.startswith('test_')]; [test() for test in tests]; print(f'{len(tests)} passed')"` and confirm the new tests fail for missing substitutions.
- [ ] Run `python -m py_compile tests/test_full_config_contract.py` and commit with `test: define temporary profile constants contract`.

### Task 2: Apply substitutions and remove magic literals

**Files:**
- Modify: `full_config.yaml`

**Interfaces:**
- Consumes: substitution names required by Task 1
- Produces: unchanged executor behavior with single-source commissioned values and named limits/timings

- [ ] Add the documented top-level substitutions before the hardware/software configuration sections.
- [ ] Remove the six commissioned `default_*` globals.
- [ ] Replace the six template-number literal `initial_value` values with their matching commissioned substitutions.
- [ ] Replace both `4294967` bounds with `${MAX_SAFE_LEASE_SECONDS}`.
- [ ] Replace both `200ms` executor delays with `${temporary_profile_modbus_settle_delay}`.
- [ ] Replace the watcher `5000U` threshold with `${temporary_profile_mode_ack_timeout_ms}U`.
- [ ] Replace every `2147483647` generation guard with `INT_MAX`.
- [ ] Run the complete assertion-preserving contract suite and expect all tests to pass.
- [ ] Run Python compilation, `git diff --check`, ID/legacy/scope checks, and review the YAML diff for unchanged lifecycle behavior.
- [ ] Commit only `full_config.yaml` with `refactor: name temporary profile constants`.

### Task 3: Final verification

**Files:**
- Verify: `full_config.yaml`
- Verify: `tests/test_full_config_contract.py`

**Interfaces:**
- Produces: fresh verification evidence; no source changes unless a discovered defect requires correction

- [ ] Run every contract through the assertion-preserving runner and record the exact pass count.
- [ ] Run `python -m py_compile tests/test_full_config_contract.py` and `git diff --check`.
- [ ] Confirm the target worktree is clean and the sibling repositories retain their pre-existing status.
- [ ] Record ESPHome CLI/config validation as unavailable if the executable remains absent.
- [ ] Request whole-branch review focused on substitution expansion inside C++ lambdas and preservation of lifecycle behavior.
