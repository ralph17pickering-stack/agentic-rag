import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def _auth_headers():
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def client():
    with patch("app.dependencies.jwt") as mock_jwt:
        mock_jwt.decode.return_value = {"sub": "user-1", "email": "test@test.com"}
        from app.main import app
        yield TestClient(app)


def test_list_blocked_tags(client):
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.order.return_value.execute.return_value.data = [
        {"id": "1", "tag": "communications plan", "created_at": "2026-01-01T00:00:00Z"},
        {"id": "2", "tag": "key findings", "created_at": "2026-01-01T00:00:00Z"},
    ]
    with patch("app.routers.documents.get_supabase_client", return_value=mock_sb):
        res = client.get("/api/documents/blocked-tags", headers=_auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert data[0]["tag"] == "communications plan"


def test_block_tag(client):
    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value.data = 5
    with patch("app.routers.documents.get_supabase_client", return_value=mock_sb):
        res = client.post(
            "/api/documents/blocked-tags",
            json={"tag": "communications plan"},
            headers=_auth_headers(),
        )
    assert res.status_code == 200
    data = res.json()
    assert data["tag"] == "communications plan"
    assert data["documents_updated"] == 5
    mock_sb.rpc.assert_called_once_with("block_tag", {"p_tag": "communications plan"})


def test_block_tag_empty_rejected(client):
    with patch("app.routers.documents.get_supabase_client"):
        res = client.post(
            "/api/documents/blocked-tags",
            json={"tag": "  "},
            headers=_auth_headers(),
        )
    assert res.status_code == 400


def test_unblock_tag(client):
    mock_sb = MagicMock()
    mock_sb.rpc.return_value.execute.return_value.data = None
    with patch("app.routers.documents.get_supabase_client", return_value=mock_sb):
        res = client.delete(
            "/api/documents/blocked-tags/communications%20plan",
            headers=_auth_headers(),
        )
    assert res.status_code == 204
    mock_sb.rpc.assert_called_once_with("unblock_tag", {"p_tag": "communications plan"})
