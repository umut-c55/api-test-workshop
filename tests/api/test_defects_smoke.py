import pytest
from http import HTTPStatus

@pytest.mark.smoke
def test_create_and_read_defect(client):
    # Anlegen
    response = client.post("/defects", json={"title": "Login hängt", "priority": 2})
    assert response.status_code == HTTPStatus.CREATED

    created = response.json()
    assert created["title"] == "Login hängt"
    assert created["priority"] == 2
    assert created["status"] == "offen"

    # Wieder lesen
    response = client.get(f"/defects/{created['id']}")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == created