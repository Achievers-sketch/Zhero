"""Digital-twin API tests (blueprint FR-03, FR-04, SIM-001)."""

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

EQ = "/api/v1/equipment"


def make(client: TestClient, equipment_id: str = "ZH-ULT-001", **extra) -> None:
    assert client.post(EQ, json={"equipment_id": equipment_id, **extra}).status_code == 201


def sim(client: TestClient, equipment_id: str = "ZH-ULT-001", **body):
    return client.post(f"{EQ}/{equipment_id}/simulate", json=body)


def values(response, variable: str) -> list[float]:
    return [r["value"] for r in response.json()["readings"] if r["variable"] == variable]


# --- SIM-001: simulated data is always marked ---


def test_simulate_marks_everything_simulated(client: TestClient) -> None:
    make(client)
    response = sim(client)
    assert response.status_code == 200
    body = response.json()
    assert body["simulation"] is True
    assert len(body["readings"]) == 4
    for reading in body["readings"]:
        assert reading["simulation"] is True
        assert reading["timestamp"].endswith("Z") or "+00:00" in reading["timestamp"]
        assert reading["unit"]
        assert reading["scenario_id"] is None
    stored = client.get(f"{EQ}/ZH-ULT-001/readings").json()
    assert stored["simulation"] is True and stored["total"] == 4
    assert all(r["simulation"] is True for r in stored["items"])


def test_simulate_without_body_works(client: TestClient) -> None:
    make(client)
    assert client.post(f"{EQ}/ZH-ULT-001/simulate").status_code == 200


def test_simulate_multiple_steps_back_dated_and_ordered(client: TestClient) -> None:
    make(client)
    response = sim(client, steps=5)
    temps = [r for r in response.json()["readings"] if r["variable"] == "internal_temperature_c"]
    stamps = [r["timestamp"] for r in temps]
    assert len(temps) == 5 and stamps == sorted(stamps)
    assert [r["step_index"] for r in temps] == [0, 1, 2, 3, 4]


# --- determinism ---


def test_same_seed_gives_same_values_on_different_equipment(client: TestClient) -> None:
    make(client, "ZH-ULT-001")
    make(client, "ZH-ULT-002")
    a = sim(client, "ZH-ULT-001", steps=6, seed=123)
    b = sim(client, "ZH-ULT-002", steps=6, seed=123)
    for variable in ("internal_temperature_c", "fan_speed_rpm", "input_voltage_v"):
        assert values(a, variable) == values(b, variable)


def test_steps_continue_across_calls(client: TestClient) -> None:
    make(client, "ZH-ULT-001")
    make(client, "ZH-ULT-002")
    sim(client, "ZH-ULT-001", steps=3, seed=7)
    second = sim(client, "ZH-ULT-001", steps=3)  # continues with the stored seed
    whole = sim(client, "ZH-ULT-002", steps=6, seed=7)
    assert values(second, "fan_speed_rpm") == values(whole, "fan_speed_rpm")[3:]


def test_validation(client: TestClient) -> None:
    make(client)
    assert sim(client, steps=0).status_code == 422
    assert sim(client, steps=101).status_code == 422
    assert sim(client, seed=-1).status_code == 422
    assert sim(client, scenario="reactor_meltdown").status_code == 422
    assert sim(client, bogus=1).status_code == 422
    assert client.post(f"{EQ}/NOPE-001/simulate").status_code == 404


# --- FR-04: faults ---


def test_cooling_degradation_end_to_end(client: TestClient) -> None:
    make(client)
    sim(client, steps=3, seed=11)
    fault = client.post(f"{EQ}/ZH-ULT-001/faults", json={"scenario": "cooling_degradation"})
    assert fault.status_code == 201
    body = fault.json()
    assert body["simulation"] is True
    assert body["status"] == "warning"
    assert body["active_scenario"] == "cooling_degradation"
    assert body["event"]["event_id"].startswith("EVT-")
    assert body["event"]["event_type"] == "SIMULATED_FAULT"
    assert body["event"]["simulation"] is True
    assert body["event"]["resolved_at"] is None
    statuses = {c["component_id"]: c["status"] for c in body["components"]}
    assert statuses["CMP-002"] == "warning" and statuses["CMP-001"] == "normal"

    response = sim(client, steps=25)
    fans = values(response, "fan_speed_rpm")
    temps = values(response, "internal_temperature_c")
    assert fans[-1] < 1800 < fans[0] + 400  # degraded below the demo band
    assert temps[-1] > temps[0] + 8
    assert {r["scenario_id"] for r in response.json()["readings"]} == {"cooling_degradation"}
    assert client.get(f"{EQ}/ZH-ULT-001").json()["status"] == "warning"


def test_power_instability_sets_power_component_warning(client: TestClient) -> None:
    make(client)
    body = client.post(f"{EQ}/ZH-ULT-001/faults", json={"scenario": "power_instability"}).json()
    assert body["status"] == "warning"
    assert {c["component_id"]: c["status"] for c in body["components"]}["CMP-001"] == "warning"
    volts = values(sim(client, steps=12), "input_voltage_v")
    assert any(v > 240 for v in volts[6:]) and any(v < 220 for v in volts[6:])


def test_component_fault_defaults_and_choice(client: TestClient) -> None:
    make(client)
    body = client.post(f"{EQ}/ZH-ULT-001/faults", json={"scenario": "component_fault"}).json()
    assert body["status"] == "fault" and body["event"]["severity"] == "fault"
    assert {c["component_id"]: c["status"] for c in body["components"]}["CMP-003"] == "fault"

    make(client, "ZH-ULT-002")
    chosen = client.post(
        f"{EQ}/ZH-ULT-002/faults", json={"scenario": "component_fault", "component_id": "CMP-004"}
    ).json()
    assert {c["component_id"]: c["status"] for c in chosen["components"]}["CMP-004"] == "fault"
    assert {c["component_id"]: c["status"] for c in chosen["components"]}["CMP-003"] == "normal"


def test_component_fault_unknown_component_404(client: TestClient) -> None:
    make(client)
    response = client.post(
        f"{EQ}/ZH-ULT-001/faults", json={"scenario": "component_fault", "component_id": "NOPE"}
    )
    assert response.status_code == 404


def test_component_id_rejected_for_other_scenarios(client: TestClient) -> None:
    make(client)
    response = client.post(
        f"{EQ}/ZH-ULT-001/faults",
        json={"scenario": "cooling_degradation", "component_id": "CMP-002"},
    )
    assert response.status_code == 422


def test_only_allow_listed_scenarios(client: TestClient) -> None:
    make(client)
    assert client.post(f"{EQ}/ZH-ULT-001/faults", json={"scenario": "x"}).status_code == 422
    assert client.post(f"{EQ}/ZH-ULT-001/faults", json={}).status_code == 422
    assert client.get(f"{EQ}/ZH-ULT-001").json()["status"] == "operational"


def test_second_fault_while_active_conflicts(client: TestClient) -> None:
    make(client)
    client.post(f"{EQ}/ZH-ULT-001/faults", json={"scenario": "cooling_degradation"})
    response = client.post(f"{EQ}/ZH-ULT-001/faults", json={"scenario": "power_instability"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "fault_active"
    assert sim(client, scenario="power_instability").status_code == 409


def test_simulate_can_trigger_scenario(client: TestClient) -> None:
    make(client)
    body = sim(client, steps=2, scenario="power_instability").json()
    assert body["active_scenario"] == "power_instability"
    assert body["event"]["scenario"] == "power_instability"
    assert {r["scenario_id"] for r in body["readings"]} == {"power_instability"}


# --- reset and history ---


def test_reset_restores_state_and_preserves_history(client: TestClient) -> None:
    make(client)
    sim(client, steps=2)
    client.post(f"{EQ}/ZH-ULT-001/faults", json={"scenario": "cooling_degradation"})
    sim(client, steps=3)
    before = client.get(f"{EQ}/ZH-ULT-001/readings").json()["total"]

    reset = client.post(f"{EQ}/ZH-ULT-001/reset")
    assert reset.status_code == 200
    body = reset.json()
    assert body["status"] == "operational" and body["active_scenario"] is None
    assert all(c["status"] == "normal" for c in body["components"])
    assert body["event"]["event_type"] == "SIMULATION_RESET"

    events = client.get(f"{EQ}/ZH-ULT-001/events").json()
    assert events["simulation"] is True and events["total"] == 2
    reset_event, fault_event = events["items"]  # newest first
    assert reset_event["event_type"] == "SIMULATION_RESET"
    assert fault_event["event_type"] == "SIMULATED_FAULT"
    assert fault_event["resolved_at"] is not None  # kept, now resolved

    assert client.get(f"{EQ}/ZH-ULT-001/readings").json()["total"] == before
    after = sim(client, steps=1).json()
    assert {r["scenario_id"] for r in after["readings"]} == {None}


def test_reset_without_active_fault_conflicts(client: TestClient) -> None:
    make(client)
    response = client.post(f"{EQ}/ZH-ULT-001/reset")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_active_fault"


def test_fault_can_be_retriggered_after_reset(client: TestClient) -> None:
    make(client)
    for _ in range(2):
        assert (
            client.post(
                f"{EQ}/ZH-ULT-001/faults", json={"scenario": "cooling_degradation"}
            ).status_code
            == 201
        )
        assert client.post(f"{EQ}/ZH-ULT-001/reset").status_code == 200
    assert client.get(f"{EQ}/ZH-ULT-001/events").json()["total"] == 4


def test_simulation_disabled_blocks_twin_actions(client: TestClient) -> None:
    make(client, simulation_enabled=False)
    for response in (
        sim(client),
        client.post(f"{EQ}/ZH-ULT-001/faults", json={"scenario": "cooling_degradation"}),
        client.post(f"{EQ}/ZH-ULT-001/reset"),
    ):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "simulation_disabled"


# --- queries ---


def test_readings_filters_and_pagination(client: TestClient) -> None:
    make(client)
    sim(client, steps=10, seed=1)
    base = f"{EQ}/ZH-ULT-001/readings"
    only = client.get(base, params={"variable": "fan_speed_rpm"}).json()
    assert only["total"] == 10 and {i["variable"] for i in only["items"]} == {"fan_speed_rpm"}
    page = client.get(base, params={"variable": "fan_speed_rpm", "limit": 3, "offset": 2}).json()
    assert [i["step_index"] for i in page["items"]] == [2, 3, 4]
    latest = client.get(base, params={"variable": "fan_speed_rpm", "order": "desc", "limit": 1})
    assert latest.json()["items"][0]["step_index"] == 9
    assert client.get(base, params={"limit": 501}).status_code == 422
    assert client.get(base, params={"order": "sideways"}).status_code == 422


def test_readings_time_range_filter(client: TestClient) -> None:
    make(client)
    stamps = [
        r["timestamp"]
        for r in sim(client, steps=4).json()["readings"]
        if r["variable"] == "fan_speed_rpm"
    ]
    base = f"{EQ}/ZH-ULT-001/readings"
    params = {"variable": "fan_speed_rpm", "from": stamps[2]}
    assert client.get(base, params=params).json()["total"] == 2
    params = {"variable": "fan_speed_rpm", "to": stamps[0]}
    assert client.get(base, params=params).json()["total"] == 1
    naive = stamps[2].replace("Z", "").split("+")[0]  # naive timestamps are read as UTC
    assert client.get(base, params={"variable": "fan_speed_rpm", "from": naive}).status_code == 200


def test_readings_and_events_missing_equipment(client: TestClient) -> None:
    assert client.get(f"{EQ}/NOPE-001/readings").status_code == 404
    assert client.get(f"{EQ}/NOPE-001/events").status_code == 404
    assert client.post(f"{EQ}/NOPE-001/reset").status_code == 404
    assert (
        client.post(f"{EQ}/NOPE-001/faults", json={"scenario": "cooling_degradation"}).status_code
        == 404
    )


def test_equipment_without_components(client: TestClient) -> None:
    make(client, "ZH-ULT-003", components=[])
    assert (
        client.post(f"{EQ}/ZH-ULT-003/faults", json={"scenario": "component_fault"}).status_code
        == 409
    )
    cooling = client.post(f"{EQ}/ZH-ULT-003/faults", json={"scenario": "cooling_degradation"})
    assert cooling.status_code == 201 and cooling.json()["components"] == []


# --- safety invariant at the database level ---


def test_database_rejects_non_simulated_readings(client: TestClient, db_engine) -> None:
    make(client)
    statement = text(
        "INSERT INTO reading"
        " (equipment_id, variable, value, unit, timestamp, simulation, step_index)"
        " VALUES ('ZH-ULT-001', 'fan_speed_rpm', 1.0, 'rpm', '2026-01-01 00:00:00', :sim, 0)"
    )
    try:
        with db_engine.begin() as conn:
            conn.execute(statement, {"sim": False})
    except IntegrityError:
        return
    raise AssertionError("A non-simulated reading was accepted by the database.")
