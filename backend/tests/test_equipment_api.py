"""Equipment API tests (blueprint FR-01, FR-02)."""

from fastapi.testclient import TestClient

BASE = "/api/v1/equipment"


def make(client: TestClient, equipment_id: str = "ZH-ULT-001", **extra):
    return client.post(BASE, json={"equipment_id": equipment_id, **extra})


def test_create_returns_profile_with_default_components(client: TestClient) -> None:
    response = make(client, location_label="Demo Room")
    assert response.status_code == 201
    body = response.json()
    assert body["equipment_id"] == "ZH-ULT-001"
    assert body["equipment_type"] == "Ultrasound"
    assert body["status"] == "operational"
    assert body["simulation_enabled"] is True
    assert body["manufacturer"] is None and body["model"] is None
    assert body["location_label"] == "Demo Room"
    assert [c["component_id"] for c in body["components"]] == [
        "CMP-001",
        "CMP-002",
        "CMP-003",
        "CMP-004",
    ]
    assert all(c["status"] == "normal" for c in body["components"])
    assert body["created_at"] and body["updated_at"]


def test_get_detail_roundtrip(client: TestClient) -> None:
    make(client)
    response = client.get(f"{BASE}/ZH-ULT-001")
    assert response.status_code == 200
    assert response.json()["equipment_id"] == "ZH-ULT-001"
    assert len(response.json()["components"]) == 4


def test_same_default_component_ids_allowed_on_different_equipment(client: TestClient) -> None:
    assert make(client, "ZH-ULT-001").status_code == 201
    assert make(client, "ZH-ULT-002").status_code == 201
    assert len(client.get(f"{BASE}/ZH-ULT-002").json()["components"]) == 4


def test_custom_and_empty_components(client: TestClient) -> None:
    custom = make(client, "ZH-ULT-010", components=[{"component_id": "X-1", "name": "Probe"}])
    assert [c["name"] for c in custom.json()["components"]] == ["Probe"]
    assert make(client, "ZH-ULT-011", components=[]).json()["components"] == []


def test_duplicate_equipment_id_conflicts(client: TestClient) -> None:
    make(client)
    response = make(client)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert response.json()["error"]["request_id"]


def test_duplicate_component_ids_rejected(client: TestClient) -> None:
    response = make(
        client,
        components=[{"component_id": "A-1", "name": "a"}, {"component_id": "A-1", "name": "b"}],
    )
    assert response.status_code == 409


def test_invalid_payloads_return_422(client: TestClient) -> None:
    assert client.post(BASE, json={}).status_code == 422
    assert make(client, "bad id!").status_code == 422
    assert make(client, equipment_type="Ventilator").status_code == 422
    body = make(client, "x").json()
    assert body["error"]["code"] == "validation_error"


def test_missing_equipment_returns_404(client: TestClient) -> None:
    response = client.get(f"{BASE}/NOPE-001")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_list_pagination_and_filters(client: TestClient) -> None:
    for i in range(1, 6):
        make(client, f"ZH-ULT-00{i}")
    page = client.get(BASE, params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 5
    assert [i["equipment_id"] for i in page["items"]] == ["ZH-ULT-003", "ZH-ULT-004"]
    assert page["limit"] == 2 and page["offset"] == 2
    assert client.get(BASE, params={"status": "fault"}).json()["total"] == 0
    assert client.get(BASE, params={"status": "operational"}).json()["total"] == 5
    assert client.get(BASE, params={"status": "bogus"}).status_code == 422
    assert client.get(BASE, params={"limit": 0}).status_code == 422
    assert client.get(BASE, params={"limit": 101}).status_code == 422


def test_patch_updates_metadata_only(client: TestClient) -> None:
    created = make(client).json()
    response = client.patch(
        f"{BASE}/ZH-ULT-001", json={"location_label": "Ward 3", "model": "Generic-1"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["location_label"] == "Ward 3"
    assert body["model"] == "Generic-1"
    assert body["status"] == "operational"
    assert body["created_at"] == created["created_at"]
    assert len(body["components"]) == 4


def test_patch_rejects_status_and_unknown_fields(client: TestClient) -> None:
    make(client)
    assert client.patch(f"{BASE}/ZH-ULT-001", json={"status": "fault"}).status_code == 422
    assert client.patch(f"{BASE}/ZH-ULT-001", json={"equipment_id": "other"}).status_code == 422
    assert client.get(f"{BASE}/ZH-ULT-001").json()["status"] == "operational"


def test_patch_missing_equipment_returns_404(client: TestClient) -> None:
    assert client.patch(f"{BASE}/NOPE-001", json={"location_label": "x"}).status_code == 404


def test_patch_can_clear_a_field(client: TestClient) -> None:
    make(client, location_label="Demo Room")
    body = client.patch(f"{BASE}/ZH-ULT-001", json={"location_label": None}).json()
    assert body["location_label"] is None
