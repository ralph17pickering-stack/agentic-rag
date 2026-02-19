def test_get_single_document(client, auth_headers, sample_document_id):
    """GET /api/documents/{id} returns the document for its owner."""
    res = client.get(f"/api/documents/{sample_document_id}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == sample_document_id


def test_get_document_not_found(client, auth_headers):
    """GET /api/documents/{id} returns 404 for non-existent id."""
    res = client.get("/api/documents/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert res.status_code == 404
