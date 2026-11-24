"""Pure simulator tests (no database)."""

import pytest

from app.digital_twin import config
from app.digital_twin.simulator import generate_step, scenario_strength


def test_same_inputs_give_identical_values() -> None:
    a = generate_step(seed=42, step_index=7)
    b = generate_step(seed=42, step_index=7)
    assert a == b


def test_different_seed_or_step_changes_values() -> None:
    base = generate_step(seed=42, step_index=7)
    assert generate_step(seed=43, step_index=7) != base
    assert generate_step(seed=42, step_index=8) != base


def test_covers_every_variable_and_normal_values_stay_in_demo_bands() -> None:
    for step in range(200):
        values = generate_step(seed=1, step_index=step)
        assert set(values) == set(config.VARIABLES)
        for name, value in values.items():
            low, high = config.DEMO_BANDS[name]
            assert low <= value <= high, (name, step, value)


def test_cooling_degradation_lowers_fan_and_raises_temperature() -> None:
    normal = generate_step(seed=5, step_index=30)
    full = generate_step(seed=5, step_index=30, scenario="cooling_degradation", scenario_step=40)
    assert full["fan_speed_rpm"] < config.DEMO_BANDS["fan_speed_rpm"][0]
    assert full["internal_temperature_c"] > config.DEMO_BANDS["internal_temperature_c"][1]
    assert full["fan_speed_rpm"] < normal["fan_speed_rpm"]
    assert full["internal_temperature_c"] > normal["internal_temperature_c"]
    # Other variables are untouched by this scenario.
    assert full["input_voltage_v"] == normal["input_voltage_v"]


def test_cooling_degradation_ramps_gradually() -> None:
    temps = [
        generate_step(seed=5, step_index=i, scenario="cooling_degradation", scenario_step=i)[
            "internal_temperature_c"
        ]
        for i in range(0, 25)
    ]
    assert temps[-1] > temps[0] + 10


def test_power_instability_pushes_voltage_out_of_band_alternating() -> None:
    low, high = config.DEMO_BANDS["input_voltage_v"]
    volts = [
        generate_step(seed=9, step_index=i, scenario="power_instability", scenario_step=i)[
            "input_voltage_v"
        ]
        for i in range(10, 16)
    ]
    assert all(v < low or v > high for v in volts)
    assert any(v > high for v in volts) and any(v < low for v in volts)


def test_component_fault_does_not_change_readings() -> None:
    assert generate_step(seed=3, step_index=4) == generate_step(
        seed=3, step_index=4, scenario="component_fault", scenario_step=2
    )


def test_unknown_scenario_rejected() -> None:
    with pytest.raises(ValueError):
        generate_step(seed=1, step_index=0, scenario="reactor_meltdown")


def test_strength_bounds() -> None:
    assert scenario_strength(None, 5) == 0.0
    assert 0 < scenario_strength("cooling_degradation", 0) < 1
    assert scenario_strength("cooling_degradation", 1000) == 1.0
