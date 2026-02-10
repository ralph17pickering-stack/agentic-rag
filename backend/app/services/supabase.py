from supabase import create_client
from app.config import settings


def get_supabase_client(access_token: str):
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client
