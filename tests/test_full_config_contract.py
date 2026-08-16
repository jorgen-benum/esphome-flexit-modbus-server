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
        definitions = re.findall(
            rf"^[ \t]*(?:-[ \t]+)?id: {re.escape(entity_id)}[ \t]*$",
            CONFIG,
            re.MULTILINE,
        )
        assert len(definitions) == 1


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


def _global_body(entity_id: str) -> str:
    block = re.search(
        rf"- id: {re.escape(entity_id)}\n(?P<body>(?:    .*\n)+?)(?=\n  - id:|\n[a-z])",
        CONFIG,
    )
    assert block is not None, f"missing global {entity_id}"
    return block.group("body")


def _script_body(script_id: str, next_script_id: str | None = None) -> str:
    end = rf"(?=\n  - id: {re.escape(next_script_id)}\n)" if next_script_id else r"(?=\n# Detect)"
    block = re.search(
        rf"  - id: {re.escape(script_id)}\n(?P<body>.*?){end}",
        CONFIG,
        re.DOTALL,
    )
    assert block is not None, f"missing script {script_id}"
    return block.group("body")


def test_async_work_has_explicit_phase_and_generation_guards() -> None:
    for entity_id in {
        "temporary_profile_phase",
        "temporary_profile_generation",
        "temporary_profile_pending_generation",
        "temporary_profile_target_observed",
    }:
        assert "restore_value: no" in _global_body(entity_id)

    apply = _script_body("temporary_profile_apply", "temporary_profile_lease_timer")
    assert "mode: single" in apply
    assert "temporary_profile_phase) == 3" in apply
    assert "temporary_profile_pending_generation) != id(temporary_profile_generation)" in apply
    assert "id(temporary_profile_apply_pending) = false" in apply

    finish = _script_body("temporary_profile_finish", "temporary_profile_restore_snapshot")
    assert "transaction != id(temporary_profile_generation)" in finish
    assert "id(temporary_profile_phase) != 3" in finish

    assert CONFIG.count("id(temporary_profile_apply).stop();") >= 2


def test_stop_is_rechecked_after_apply_delay_before_mode_command() -> None:
    apply = _script_body("temporary_profile_apply", "temporary_profile_lease_timer")
    delayed = apply.index("- delay: 200ms")
    stop_recheck = apply.index("flexit_modbus_server::REG_MODE", delayed)
    stop_branch = apply.index("current_mode == 0", stop_recheck)
    mode_command = apply.index("mode_call.set_option(target_mode)", stop_branch)
    assert delayed < stop_recheck < stop_branch < mode_command
    assert "temporary_profile_restore_snapshot" in apply[stop_branch:mode_command]
    assert "temporary_profile_clear_owner" in apply[stop_branch:mode_command]


def test_acknowledgement_and_expiry_detect_native_takeover() -> None:
    lease = _script_body("temporary_profile_lease_timer", "temporary_profile_finish")
    assert "transaction != id(temporary_profile_generation)" in lease
    assert "actual != expected" in lease
    assert "Running native takeover detected at lease expiry" in lease
    assert "temporary_profile_clear_owner" in lease

    watcher = CONFIG[CONFIG.index("interval:\n  - interval: 1s"):]
    stop_check = watcher.index("actual == 0")
    acknowledgement_guard = watcher.index("!id(temporary_profile_target_observed)")
    assert stop_check < acknowledgement_guard
    assert "id(temporary_profile_target_observed) = true" in watcher
    assert "temporary_profile_change_ms)) < 5000U" in watcher
    assert "Running native takeover detected" in watcher


def test_apply_validates_before_mutating_lease_or_diagnostics() -> None:
    apply = _script_body("temporary_profile_apply", "temporary_profile_lease_timer")
    first_mutation = apply.index("id(temporary_profile_lease_seconds) = lease_seconds")
    assert apply.index("Unsupported target mode") < first_mutation
    assert apply.index("Cannot change target mode") < first_mutation
    assert apply.index("temporary_profile_phase) == 3") < first_mutation
    assert apply.index("current_mode == 0") < first_mutation


def test_commissioned_template_numbers_have_safe_initial_state() -> None:
    commissioned = {
        "supply_air_percentage_min": "50.0",
        "extract_air_percentage_min": "50.0",
        "supply_air_percentage_normal": "60.0",
        "extract_air_percentage_normal": "57.0",
        "supply_air_percentage_max": "100.0",
        "extract_air_percentage_max": "100.0",
    }
    for entity_id, value in commissioned.items():
        block = re.search(
            rf"  - platform: template\n    id: {re.escape(entity_id)}\n(?P<body>.*?)(?=\n  - platform:|\n[a-z])",
            CONFIG,
            re.DOTALL,
        )
        assert block is not None, f"missing template number {entity_id}"
        body = block.group("body")
        assert f"initial_value: {value}" in body
        assert "optimistic: True" in body
        assert "restore_value: True" in body
        assert "set_action:" in body

    assert "does not invoke set_action or write Modbus at boot" in CONFIG
