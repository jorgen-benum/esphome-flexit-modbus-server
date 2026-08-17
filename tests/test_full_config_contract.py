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


def test_commissioned_profiles_use_documented_substitutions() -> None:
    commissioned = {
        "commissioned_supply_fan_min": "50.0",
        "commissioned_extract_fan_min": "50.0",
        "commissioned_supply_fan_normal": "60.0",
        "commissioned_extract_fan_normal": "57.0",
        "commissioned_supply_fan_max": "100.0",
        "commissioned_extract_fan_max": "100.0",
    }
    substitutions = CONFIG[: CONFIG.index("globals:\n")]
    assert "substitutions:\n" in substitutions
    assert "commissioned" in substitutions.lower()
    for name, value in commissioned.items():
        assert f'{name}: "{value}"' in substitutions

    assert 'MAX_SAFE_LEASE_SECONDS: "43200"' in substitutions
    assert "12 hours" in substitutions
    assert 'temporary_profile_modbus_settle_delay: "200ms"' in substitutions
    assert 'temporary_profile_mode_ack_timeout_ms: "5000"' in substitutions

    for obsolete_global in {
        "default_supply_fan_min",
        "default_extract_fan_min",
        "default_supply_fan_normal",
        "default_extract_fan_normal",
        "default_supply_fan_max",
        "default_extract_fan_max",
    }:
        assert f"id: {obsolete_global}" not in CONFIG


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
    delayed = apply.index("- delay: ${temporary_profile_modbus_settle_delay}")
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
    assert "temporary_profile_change_ms)) < ${temporary_profile_mode_ack_timeout_ms}U" in watcher
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
        "supply_air_percentage_min": "commissioned_supply_fan_min",
        "extract_air_percentage_min": "commissioned_extract_fan_min",
        "supply_air_percentage_normal": "commissioned_supply_fan_normal",
        "extract_air_percentage_normal": "commissioned_extract_fan_normal",
        "supply_air_percentage_max": "commissioned_supply_fan_max",
        "extract_air_percentage_max": "commissioned_extract_fan_max",
    }
    for entity_id, value in commissioned.items():
        block = re.search(
            rf"  - platform: template\n    id: {re.escape(entity_id)}\n(?P<body>.*?)(?=\n  - platform:|\n[a-z])",
            CONFIG,
            re.DOTALL,
        )
        assert block is not None, f"missing template number {entity_id}"
        body = block.group("body")
        assert f"initial_value: ${{{value}}}" in body
        assert "optimistic: True" in body
        assert "restore_value: True" in body
        assert "set_action:" in body

    assert "does not invoke set_action or write Modbus at boot" in CONFIG


def test_script_parameters_use_supported_types_and_safe_signed_bounds() -> None:
    scripts = CONFIG[CONFIG.index("script:\n"):]
    parameter_types = re.findall(
        r"^      [a-z_]+: ([a-zA-Z0-9_:]+)$",
        scripts,
        re.MULTILINE,
    )
    assert "uint32_t" not in parameter_types
    assert "transaction: int" in scripts
    assert "lease_seconds: int" in scripts
    assert "delay_ms:" not in scripts
    assert "type: int" in _global_body("temporary_profile_generation")
    assert "type: int" in _global_body("temporary_profile_pending_generation")

    apply = _script_body("temporary_profile_apply", "temporary_profile_lease_timer")
    assert "lease_seconds > ${MAX_SAFE_LEASE_SECONDS}" in apply
    assert "4294967" not in CONFIG
    assert "++id(temporary_profile_generation)" not in CONFIG
    assert CONFIG.count("temporary_profile_generation) >= std::numeric_limits<int>::max()") >= 4
    assert "2147483647" not in CONFIG
    assert " >= INT_MAX" not in CONFIG


def test_pending_running_native_takeover_is_not_overwritten() -> None:
    assert "restore_value: no" in _global_body("temporary_profile_pre_apply_mode")
    apply = _script_body("temporary_profile_apply", "temporary_profile_lease_timer")
    delayed = apply[apply.index("- delay: ${temporary_profile_modbus_settle_delay}"):]
    assert "actual != id(temporary_profile_pre_apply_mode)" in delayed
    assert "actual != expected_target" in delayed
    takeover = delayed.index("Running native takeover detected during pending apply")
    clear = delayed.index("temporary_profile_clear_owner", takeover)
    assert "temporary_profile_restore_snapshot" not in delayed[takeover:clear]
    assert takeover < clear < delayed.index("mode_call.set_option(target_mode)")


def test_release_before_acknowledgement_restores_original_snapshot() -> None:
    finish = _script_body("temporary_profile_finish", "temporary_profile_restore_snapshot")
    assert "original_mode_unacknowledged" in finish
    assert "!id(temporary_profile_target_observed)" in finish
    assert "actual == id(temporary_profile_pre_apply_mode)" in finish
    assert "actual != expected && !original_mode_unacknowledged" in finish
    assert "actual != flexit_modbus_server::string_to_mode(\"Normal\")" in finish
    assert finish.index("original_mode_unacknowledged") < finish.index('mode_call.set_option("Normal")')
    assert finish.count("original_mode_unacknowledged") >= 2
    assert "executor_mode_still_observed" in finish
    assert "!executor_mode_still_observed" in finish


def test_expiry_before_acknowledgement_restores_original_snapshot() -> None:
    lease = _script_body("temporary_profile_lease_timer", "temporary_profile_finish")
    assert "original_mode_unacknowledged" in lease
    assert "!id(temporary_profile_target_observed)" in lease
    assert "actual == id(temporary_profile_pre_apply_mode)" in lease
    assert "actual != expected && !original_mode_unacknowledged" in lease
    assert "temporary_profile_finish" in lease


def test_terminal_apply_paths_do_not_enter_the_delay() -> None:
    apply = _script_body("temporary_profile_apply", "temporary_profile_lease_timer")
    guard = apply.index("      - if:\n          condition:")
    delay = apply.index("- delay: ${temporary_profile_modbus_settle_delay}")
    assert guard < delay
    guard_body = apply[guard:delay]
    assert "return id(temporary_profile_apply_pending)" in guard_body
    assert "temporary_profile_pending_generation) == id(temporary_profile_generation)" in guard_body

    renewal = apply.index("if (same_request)")
    renewal_return = apply.index("return;", renewal)
    assert renewal < renewal_return < guard


def test_named_timing_constants_replace_executor_literals() -> None:
    scripts = CONFIG[CONFIG.index("script:\n"):]
    watcher = CONFIG[CONFIG.index("interval:\n  - interval: 1s"):]

    assert scripts.count("delay: ${temporary_profile_modbus_settle_delay}") == 2
    assert "delay: 200ms" not in scripts
    assert "lease_seconds > ${MAX_SAFE_LEASE_SECONDS}" in scripts
    assert "lease_seconds > 4294967" not in scripts
    assert "${temporary_profile_mode_ack_timeout_ms}U" in watcher
    assert "5000U" not in watcher
