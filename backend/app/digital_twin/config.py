"""Demo configuration for the simulated ultrasound digital twin.

*** EVERY VALUE IN THIS FILE IS A SYNTHETIC, ILLUSTRATIVE ASSUMPTION. ***

None of these numbers come from a manufacturer, a service manual or a real device.
They exist only to make the simulation behave plausibly for a demonstration. They must
not be presented as manufacturer limits, calibration specifications or validated
diagnostic signatures. Replace them with documented, model-specific values (recording
source, revision and page) before any real-world claim is made.
"""

from dataclasses import dataclass
from typing import Literal, get_args

# Seconds between consecutive simulated samples (used to back-date timestamps).
SIMULATION_INTERVAL_S = 5


@dataclass(frozen=True)
class VariableSpec:
    unit: str
    nominal: float  # synthetic "normal operation" centre value
    noise: float  # standard deviation of synthetic noise


VARIABLES: dict[str, VariableSpec] = {
    "internal_temperature_c": VariableSpec(unit="C", nominal=38.0, noise=0.6),
    "input_voltage_v": VariableSpec(unit="V", nominal=230.0, noise=1.5),
    "fan_speed_rpm": VariableSpec(unit="rpm", nominal=2000.0, noise=40.0),
    "system_load_pct": VariableSpec(unit="%", nominal=40.0, noise=6.0),
}

# Synthetic demo bands used by the dashboard and tests to describe "within normal demo range".
DEMO_BANDS: dict[str, tuple[float, float]] = {
    "internal_temperature_c": (34.0, 43.0),
    "input_voltage_v": (220.0, 240.0),
    "fan_speed_rpm": (1800.0, 2200.0),
    "system_load_pct": (10.0, 75.0),
}

ScenarioId = Literal["cooling_degradation", "power_instability", "component_fault"]
SCENARIO_IDS: tuple[str, ...] = get_args(ScenarioId)


@dataclass(frozen=True)
class ScenarioSpec:
    label: str
    severity: Literal["warning", "fault"]
    description: str
    default_component_id: str  # component affected when the client does not choose one
    ramp_steps: int = 1  # steps for the anomaly to reach full strength


SCENARIOS: dict[str, ScenarioSpec] = {
    "cooling_degradation": ScenarioSpec(
        label="Cooling degradation",
        severity="warning",
        description="Synthetic cooling subsystem anomaly introduced for demonstration.",
        default_component_id="CMP-002",
        ramp_steps=20,
    ),
    "power_instability": ScenarioSpec(
        label="Power instability",
        severity="warning",
        description="Synthetic input-voltage instability introduced for demonstration.",
        default_component_id="CMP-001",
        ramp_steps=5,
    ),
    "component_fault": ScenarioSpec(
        label="Component fault",
        severity="fault",
        description="Synthetic component fault introduced for demonstration.",
        default_component_id="CMP-003",
    ),
}

# Strength of the synthetic anomalies at full ramp.
COOLING_FAN_DROP_FRACTION = 0.55  # fan speed falls by this fraction of nominal
COOLING_TEMP_RISE_C = 16.0  # temperature rises by this many degrees C
POWER_VOLTAGE_SWING_V = 35.0  # voltage alternates +/- this far from nominal
