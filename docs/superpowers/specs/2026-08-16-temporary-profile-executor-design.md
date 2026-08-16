# Inline Temporary-Profile Executor Design

## Goal

Update `full_config.yaml` so it implements the temporary-profile executor required by the `flexit_ventilation_control` Home Assistant integration. The executor design is currently drafted in the separate `flexit_ventilation_control/flexit_temporary_profile.yaml` file; its finished implementation belongs inline in this repository's full configuration example.

`ESP-ModbusRTUServer` and the `flexit_ventilation_control` repository remain unchanged.

## Scope

Use a focused inline replacement:

- Remove the old fireplace-specific globals, switch, number controls, conflict sensor, and timer.
- Inline the generic temporary-profile executor into the existing matching YAML sections.
- Preserve all unrelated Flexit switches, buttons, numbers, sensors, binary sensors, and text sensors.
- Preserve the existing IDs used by the executor: `server`, `set_mode`, the MIN/NORMAL/MAX supply numbers, and the MIN/NORMAL/MAX extract numbers.
- Do not reorganize the rest of the full configuration.

## Commissioned profiles

Keep these installation-specific commissioned values as non-restored globals and label them clearly as commissioned values:

| Profile | Supply | Extract |
| --- | ---: | ---: |
| MIN | 50% | 50% |
| NORMAL | 60% | 57% |
| MAX | 100% | 100% |

These values document the commissioned installation and provide fallbacks. They are not automatically written to the Flexit controller at boot.

## ESPHome interface

Expose two ESPHome API actions:

- `apply_temporary_profile(owner, target_mode, supply, extract, lease_seconds)`
- `release_temporary_profile(owner)`

Expose these Home Assistant entities:

- `Temporary Profile Owner`
- `Temporary Profile Lease Remaining`

The owner is an opaque string. The ESPHome executor does not encode policy for particular owners such as `humidity` or `fireplace`.

## Apply and renewal behavior

On the first accepted request, snapshot the supply and extract settings of the target profile, apply the temporary values, select the target mode, record the owner, and start the safety lease.

If a new owner replaces the current owner on the same target mode, retain the first owner's original restore snapshot. This prevents a transition such as humidity to fireplace from treating the humidity settings as the baseline.

An identical request—same owner, target mode, supply, and extract—renews only the lease. It must not rewrite profile values or reassert the mode.

Reject requests with an empty owner, a non-positive lease, a `Stop` target, an unsupported target mode, or while the Flexit unit is stopped. Reject a change of target mode while a temporary profile is active because the executor has only one restore snapshot.

## Release, expiry, and takeover

Explicit release is owner-checked. A stale release from one owner cannot cancel a newer owner's request.

On an accepted release or lease expiry:

1. Return the Flexit unit to Normal unless it is stopped.
2. Restore the original supply and extract snapshot for the overridden profile.
3. Clear ownership and lease state.

If an external panel, kitchen input, or other native source changes to another running mode, stop the lease and clear ownership without changing the externally selected mode or immediately restoring the overridden profile.

If the external change is Stop, restore the overridden profile and clear ownership, but never command the Flexit unit away from Stop.

## Restart behavior

Temporary ownership, lease state, and the restore snapshot are volatile (`restore_value: no`). After an ESP restart, the executor reports no owner, does not resume a lease, and does not make speculative Modbus writes. This avoids claiming or modifying a state that may have been changed by native Flexit controls while the executor was unavailable.

The trade-off is that a pre-request restore snapshot cannot be recovered after an ESP restart.

## Verification

Verify the change by:

1. Checking that the completed YAML retains all required executor dependency IDs.
2. Checking that each new executor ID is defined once and all references resolve.
3. Confirming that all legacy fireplace globals and entities are absent.
4. Parsing or validating the YAML with ESPHome-aware tooling where available.
5. Running an ESPHome configuration or compile check if the CLI and required base configuration are available.
6. Reviewing the Git diff to confirm only the agreed configuration and supporting plan/specification files changed, while preserving the existing untracked `input temp.txt`.
