import pytest

from tests.support import local_supabase


@pytest.fixture(scope="session")
def supabase_stack():
    """The local Supabase stack. Skips (loudly) when it is not running: `supabase start`."""
    found = local_supabase.stack()
    if found is None:
        pytest.skip("local Supabase is not running: install Docker + the CLI, run `supabase start`")
    return found
