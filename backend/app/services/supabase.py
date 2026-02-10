from supabase import create_client
from app.config import settings


def get_supabase_client(access_token: str):
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client


def get_service_supabase_client():
    """Supabase client using service role key — bypasses RLS.
    Used for background ingestion tasks where no user JWT is available."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
