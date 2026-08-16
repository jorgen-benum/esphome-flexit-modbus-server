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
