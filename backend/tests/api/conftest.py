import pytest


@pytest.fixture
def categories(client) -> dict[str, dict]:
    """Danh mục seed (theo slug)."""
    resp = client.get("/api/v1/categories")
    assert resp.status_code == 200
    return {c["slug"]: c for c in resp.json()}
