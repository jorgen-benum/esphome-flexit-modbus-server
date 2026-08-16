# Inline Temporary-Profile Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fireplace-only automation in `full_config.yaml` with the generic, leased temporary-profile executor required by the Home Assistant `flexit_ventilation_control` integration.

**Architecture:** Keep the existing Flexit Modbus entities and inline the executor drafted in the sibling repository's `flexit_temporary_profile.yaml`. Home Assistant supplies policy through owner-checked ESPHome API actions; the ESP node owns profile snapshots, lease expiry, external-takeover detection, and safe restoration.

**Tech Stack:** ESPHome YAML, ESPHome template entities/actions/scripts, embedded C++ lambdas, Python/pytest contract tests

## Global Constraints

- Modify behavior only in `esphome-flexit-modbus-server`; do not change `ESP-ModbusRTUServer` or `flexit_ventilation_control`.
- Preserve every unrelated Flexit switch, button, number, select, sensor, binary sensor, and text sensor in `full_config.yaml`.
- Preserve IDs `server`, `set_mode`, `supply_air_percentage_min`, `supply_air_percentage_normal`, `supply_air_percentage_max`, `extract_air_percentage_min`, `extract_air_percentage_normal`, and `extract_air_percentage_max`.
- Remove the old fireplace-specific globals, switch, number controls, conflict sensor, and timer.
- Keep commissioned MIN supply/extract at `50.0/50.0`, NORMAL at `60.0/57.0`, and MAX at `100.0/100.0`; label all six as commissioned values.
- Commissioned globals use `restore_value: no` and are never automatically written at boot.
- Ownership, lease state, and restore snapshots remain volatile with `restore_value: no`.
- Preserve the existing untracked `input temp.txt` without modifying or staging it.

## File Structure

- Create `tests/test_full_config_contract.py`: text-level regression contract for required IDs, commissioned values, API interface, safety behavior markers, and removal of the legacy fireplace executor.
- Modify `full_config.yaml`: retain the low-level Modbus configuration and entities while inlining the generic temporary-profile executor.
- Do not modify `README.md` in this change; the task is limited to completing the full configuration example.

---

### Task 1: Add the temporary-profile configuration contract

**Files:**
- Create: `tests/test_full_config_contract.py`

**Interfaces:**
- Consumes: repository-root `full_config.yaml` as UTF-8 text
- Produces: pytest assertions defining the required executor IDs, action fields, commissioned profile values, and forbidden legacy IDs

- [ ] **Step 1: Write the failing contract test**

Create `tests/test_full_config_contract.py` with this exact content:

```python
from pathlib import Path
import re


CONFIG = (Path(__file__).parents[1] / "full_config.yaml").read_text()


def test_generic_temporary_profile_interface_is_inlined() -> None:
    required_fragments = {
        "api actions": "api:\n  actions:",
        "apply action": "action: apply_temporary_profile",
        "release action": "action: release_temporary_profile",
        "owner input": "owner: string",
        "target mode input": "target_mode: string",
        "supply input": "supply: float",
        "extract input": "extract: float",
        "lease input": "lease_seconds: int",
        "owner sensor": 'name: "Temporary Profile Owner"',
        "lease sensor": 'name: "Temporary Profile Lease Remaining"',
        "external mode watcher": "interval:\n  - interval: 1s",
    }
    for label, fragment in required_fragments.items():
        assert fragment in CONFIG, f"missing {label}: {fragment}"


def test_commissioned_profiles_are_documented_and_non_restored() -> None:
    commissioned = {
        "default_supply_fan_min": "50.0",
        "default_extract_fan_min": "50.0",
        "default_supply_fan_normal": "60.0",
        "default_extract_fan_normal": "57.0",
        "default_supply_fan_max": "100.0",
        "default_extract_fan_max": "100.0",
    }
    for entity_id, value in commissioned.items():
        block = re.search(
            rf"- id: {entity_id}\n(?P<body>(?:    .*\n)+?)(?=\n  - id:|\n[a-z])",
            CONFIG,
        )
        assert block is not None, f"missing commissioned global {entity_id}"
        body = block.group("body")
        assert "restore_value: no" in body
        assert f"initial_value: '{value}'" in body
        assert "commissioned" in body.lower()


def test_executor_state_is_volatile() -> None:
    volatile_ids = {
        "temporary_profile_active",
        "temporary_profile_owner",
        "temporary_profile_target_mode",
        "temporary_profile_supply",
        "temporary_profile_extract",
        "temporary_profile_restore_supply",
        "temporary_profile_restore_extract",
        "temporary_profile_lease_seconds",
        "temporary_profile_lease_started_ms",
        "temporary_profile_change_ms",
        "temporary_profile_apply_pending",
    }
    for entity_id in volatile_ids:
        block = re.search(
            rf"- id: {entity_id}\n(?P<body>(?:    .*\n)+?)(?=\n  - id:|\n[a-z])",
            CONFIG,
        )
        assert block is not None, f"missing executor global {entity_id}"
        assert "restore_value: no" in block.group("body")


def test_legacy_fireplace_executor_is_removed() -> None:
    legacy_ids = {
        "fireplace_mode_active",
        "previous_mode_before_fireplace",
        "fireplace_duration_minutes",
        "original_supply_fan_max",
        "original_extract_fan_max",
        "fireplace_supply_fan_speed",
        "fireplace_extract_fan_speed",
        "fireplace_mode_change_timestamp",
        "fireplace_mode_switch",
        "fireplace_duration",
        "fireplace_supply_speed_control",
        "fireplace_extract_speed_control",
        "fireplace_conflict",
        "fireplace_timer",
    }
    for entity_id in legacy_ids:
        assert f"id: {entity_id}" not in CONFIG


def test_existing_executor_dependencies_remain_unique() -> None:
    dependency_ids = {
        "server",
        "set_mode",
        "supply_air_percentage_min",
        "supply_air_percentage_normal",
        "supply_air_percentage_max",
        "extract_air_percentage_min",
        "extract_air_percentage_normal",
        "extract_air_percentage_max",
    }
    for entity_id in dependency_ids:
        assert len(re.findall(rf"^\s*- id: {entity_id}$", CONFIG, re.MULTILINE)) == 1


def test_safety_paths_are_present() -> None:
    required_fragments = {
        'target_mode == "Stop"',
        "current_mode == 0",
        "same_request",
        'id(temporary_profile_owner) == owner',
        'call.set_option("Normal")',
        "temporary_profile_restore_snapshot",
        "temporary_profile_clear_owner",
        "actual != expected",
    }
    for fragment in required_fragments:
        assert fragment in CONFIG, f"missing safety behavior: {fragment}"
```

- [ ] **Step 2: Run the contract test and verify that the old configuration fails**

Run:

```bash
python -m pytest tests/test_full_config_contract.py -v
```

Expected: failures for the absent `api.actions`, temporary-profile globals/entities, commissioned globals, and the still-present legacy fireplace IDs. If pytest is unavailable, record that limitation and run `python -m py_compile tests/test_full_config_contract.py` to verify test syntax before continuing.

- [ ] **Step 3: Commit the failing contract**

```bash
git add tests/test_full_config_contract.py
git commit -m "test: define temporary profile config contract"
```

Expected: only the new contract test is committed; `input temp.txt` remains untracked.

---

### Task 2: Inline the generic executor and remove the fireplace executor

**Files:**
- Modify: `full_config.yaml:44-220`
- Modify: `full_config.yaml:448-495`
- Modify: `full_config.yaml:518-699`
- Modify: `full_config.yaml:783-830`
- Reference without modifying: `../flexit_ventilation_control/flexit_temporary_profile.yaml`

**Interfaces:**
- Consumes: existing `server`, `set_mode`, and six MIN/NORMAL/MAX supply/extract number IDs
- Produces: `apply_temporary_profile(owner: string, target_mode: string, supply: float, extract: float, lease_seconds: int)`, `release_temporary_profile(owner: string)`, text sensor `temporary_profile_owner_sensor`, and numeric sensor `temporary_profile_lease_remaining`

- [ ] **Step 1: Replace the legacy globals with commissioned profiles and volatile executor state**

Replace the complete old `globals:` contents with the `globals:` section from `../flexit_ventilation_control/flexit_temporary_profile.yaml`. Keep the values unchanged, but make every profile comment explicitly identify it as commissioned:

```yaml
globals:
  - id: default_supply_fan_min
    type: float
    restore_value: no
    initial_value: '50.0'  # Commissioned MIN supply

  - id: default_extract_fan_min
    type: float
    restore_value: no
    initial_value: '50.0'  # Commissioned MIN extract

  - id: default_supply_fan_normal
    type: float
    restore_value: no
    initial_value: '60.0'  # Commissioned NORMAL supply

  - id: default_extract_fan_normal
    type: float
    restore_value: no
    initial_value: '57.0'  # Commissioned NORMAL extract

  - id: default_supply_fan_max
    type: float
    restore_value: no
    initial_value: '100.0'  # Commissioned MAX supply

  - id: default_extract_fan_max
    type: float
    restore_value: no
    initial_value: '100.0'  # Commissioned MAX extract
```

After these six entries, copy the draft globals from `temporary_profile_active` through `temporary_profile_apply_pending` verbatim. Do not add boot-time automations that write the six defaults.

- [ ] **Step 2: Add the API actions verbatim from the approved draft**

Insert the exact `api:` section from `../flexit_ventilation_control/flexit_temporary_profile.yaml`, beginning at `api:` and ending immediately before its top-level `script:` key, between `globals:` and `switch:`. Do not copy the draft's `script:` key in this step. Verify the extracted source before inserting it:

```bash
sed -n '/^api:$/,/^script:$/p' ../flexit_ventilation_control/flexit_temporary_profile.yaml
```

Expected: output starts with `api:`, contains both actions, and ends with the unindented `script:` boundary. Insert every line before that boundary exactly. This source contains every approved validation, snapshot, renewal, replacement, write, delay, mode-selection, timer, and diagnostic-update branch.

- [ ] **Step 3: Remove only the old fireplace entities**

Delete these complete YAML entries while leaving their surrounding sections and unrelated entries intact:

```text
switch.fireplace_mode_switch
number.fireplace_duration
number.fireplace_supply_speed_control
number.fireplace_extract_speed_control
binary_sensor.fireplace_conflict
script.fireplace_timer
```

- [ ] **Step 4: Add scripts, takeover watcher, and diagnostic entities from the approved draft**

Copy these complete sections/entries verbatim from `../flexit_ventilation_control/flexit_temporary_profile.yaml` into the matching top-level sections of `full_config.yaml`:

```text
script.temporary_profile_lease_timer
script.temporary_profile_finish
script.temporary_profile_restore_snapshot
script.temporary_profile_clear_owner
interval (the 1-second external mode watcher)
text_sensor.temporary_profile_owner_sensor
sensor.temporary_profile_lease_remaining
```

Merge the new `sensor` and `text_sensor` entries into the existing sections; do not introduce duplicate top-level `sensor:` or `text_sensor:` keys. The new `script:` and `interval:` sections may use the draft ordering. Preserve the draft's 5-second self-change guard, protected-Stop branch, owner clearing, lease countdown, and `none` owner output.

- [ ] **Step 5: Run the focused contract test**

Run:

```bash
python -m pytest tests/test_full_config_contract.py -v
```

Expected: `6 passed`. If pytest was unavailable in Task 1, install nothing; instead record the limitation and run the equivalent repository-local Python assertions only if an already-available Python test runner supports them.

- [ ] **Step 6: Inspect the structural diff and whitespace**

Run:

```bash
git diff --check
git diff -- full_config.yaml
git status --short
```

Expected: no whitespace errors; the YAML diff contains only the executor replacement and commissioned comments; `input temp.txt` is still shown as untracked and unstaged.

- [ ] **Step 7: Commit the executor replacement**

```bash
git add full_config.yaml
git commit -m "feat: add generic temporary profile executor"
```

Expected: the commit contains only `full_config.yaml`.

---

### Task 3: Validate the integrated configuration

**Files:**
- Verify: `full_config.yaml`
- Verify: `tests/test_full_config_contract.py`

**Interfaces:**
- Consumes: completed inline executor and its existing entity dependencies
- Produces: verification evidence; no new runtime interface

- [ ] **Step 1: Run the complete repository test suite**

```bash
python -m pytest -v
```

Expected: all tests pass, including all six contract tests.

- [ ] **Step 2: Check executor ID definitions and legacy removal independently**

```bash
python - <<'PY'
from pathlib import Path
import re

text = Path("full_config.yaml").read_text()
required = [
    "temporary_profile_active",
    "temporary_profile_owner",
    "temporary_profile_target_mode",
    "temporary_profile_lease_timer",
    "temporary_profile_finish",
    "temporary_profile_restore_snapshot",
    "temporary_profile_clear_owner",
    "temporary_profile_owner_sensor",
    "temporary_profile_lease_remaining",
]
legacy = ["fireplace_mode_switch", "fireplace_conflict", "fireplace_timer"]
for entity_id in required:
    assert re.search(rf"^\s*- id: {entity_id}$", text, re.MULTILINE), entity_id
for entity_id in legacy:
    assert f"id: {entity_id}" not in text, entity_id
print("executor ID check passed")
PY
```

Expected: `executor ID check passed`.

- [ ] **Step 3: Run ESPHome validation when available**

First run:

```bash
command -v esphome
```

The current environment is expected not to print a path. If it does print a path and the local deployment wrapper supplies required base ESPHome keys such as `esphome`, `wifi`, and `api`, run that wrapper's normal `esphome config` command against the composed configuration. Do not alter `full_config.yaml` merely to make this repository example standalone. Record ESPHome validation as unavailable when the CLI or deployment wrapper is absent.

- [ ] **Step 4: Perform final repository-scope verification**

```bash
git diff HEAD~2..HEAD --check
git diff HEAD~2..HEAD --stat
git status --short
```

Expected: the two implementation commits contain only `tests/test_full_config_contract.py` and `full_config.yaml`; the earlier approved design and plan commits are separate; `input temp.txt` remains untracked and no files in the other two repositories changed.

- [ ] **Step 5: Record verification without creating an empty commit**

If every check passes, report the exact commands and results in the handoff. If a validation check requires a corrective edit, make the smallest correction, rerun all checks, and commit only that correction with:

```bash
git add full_config.yaml tests/test_full_config_contract.py
git commit -m "fix: satisfy temporary profile config validation"
```
