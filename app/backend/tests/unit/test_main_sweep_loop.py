def test_sweep_loop_exists():
    """Verify main.py has the sweep loop function."""
    from app.main import _tag_quality_sweep_loop
    assert callable(_tag_quality_sweep_loop)
