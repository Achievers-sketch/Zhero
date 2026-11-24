"""Deterministic synthetic-reading generator (no database, no I/O).

``generate_step`` is a pure function of its arguments: the same
(seed, step_index, scenario, scenario_step) always returns the same values, which makes
simulation runs reproducible in tests. All output is SIMULATED data.
"""

import random

from app.digital_twin import config


def scenario_strength(scenario: str | None, scenario_step: int) -> float:
    """Return 0..1 anomaly strength, ramping up over the scenario's ramp_steps."""
    if scenario is None:
        return 0.0
    ramp = config.SCENARIOS[scenario].ramp_steps
    return min(1.0, (scenario_step + 1) / ramp)


def generate_step(
    *,
    seed: int,
    step_index: int,
    scenario: str | None = None,
    scenario_step: int = 0,
) -> dict[str, float]:
    """Generate one synthetic sample of every simulation variable.

    Args:
        seed: Run seed; fixes the noise sequence.
        step_index: Global step counter for the equipment (selects the noise sample).
        scenario: Active allow-listed scenario id, or None for normal operation.
        scenario_step: Steps elapsed since the scenario started (drives the ramp).
    """
    if scenario is not None and scenario not in config.SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario!r}")

    rng = random.Random(f"{seed}:{step_index}")
    values = {
        name: spec.nominal + rng.gauss(0.0, spec.noise) for name, spec in config.VARIABLES.items()
    }

    strength = scenario_strength(scenario, scenario_step)
    if scenario == "cooling_degradation":
        fan_nominal = config.VARIABLES["fan_speed_rpm"].nominal
        values["fan_speed_rpm"] -= fan_nominal * config.COOLING_FAN_DROP_FRACTION * strength
        values["internal_temperature_c"] += config.COOLING_TEMP_RISE_C * strength
    elif scenario == "power_instability":
        sign = 1.0 if scenario_step % 2 == 0 else -1.0
        values["input_voltage_v"] += sign * config.POWER_VOLTAGE_SWING_V * strength
    # component_fault changes component state only, not the readings.

    values["system_load_pct"] = min(100.0, max(0.0, values["system_load_pct"]))
    return {name: round(value, 2) for name, value in values.items()}
