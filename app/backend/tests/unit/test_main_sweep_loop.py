def test_sweep_loop_exists():
    """Verify main.py has the sweep loop function."""
    from app.main import _tag_quality_sweep_loop
    assert callable(_tag_quality_sweep_loop)


def test_enrichment_loop_exists():
    from app.main import _tag_enrichment_sweep_loop
    assert callable(_tag_enrichment_sweep_loop)


def test_activity_middleware_records_on_request():
    """A real HTTP request to the app should update _last_activity."""
    import app.services.activity as act
    from datetime import datetime, timezone, timedelta
    from fastapi.testclient import TestClient
    from app.main import app

    # Set activity to old timestamp
    act._last_activity = datetime.now(timezone.utc) - timedelta(hours=1)
    before = act._last_activity

    client = TestClient(app)
    client.get("/health")

    assert act._last_activity > before
