from app.config import Settings


def test_tag_settings_defaults():
    s = Settings(
        supabase_url="http://x",
        supabase_anon_key="x",
        supabase_service_role_key="x",
        supabase_jwt_secret="x",
    )
    assert s.tag_candidates == 15
    assert s.tag_max_per_document == 8
    assert s.tag_quality_sweep_enabled is True
    assert s.tag_quality_sweep_interval_hours == 12
    assert s.tag_quality_sweep_sample_size == 10
    assert s.tag_quality_auto_block_threshold == 3
