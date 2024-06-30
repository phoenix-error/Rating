from os import environ

from dotenv import load_dotenv

load_dotenv()


def test_env_vars_from_env_file():
    assert environ["SUPABASE_USER"] == "postgres"
    assert environ["SUPABASE_PASSWORD"] == "postgres"
    assert environ["SUPABASE_HOST"] == "127.0.0.1"
    assert environ["SUPABASE_PORT"] == "54322"
    assert environ["SUPABASE_NAME"] == "postgres"
    assert environ["SUPABASE_URL"] == "http://127.0.0.1:54321"
    assert (
        environ["SUPABASE_KEY"]
        == "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
    )
