"""Backend composition: select review persistence, then inject it into the agent."""

import logging
import os
from pathlib import Path

from dotenv import dotenv_values
from langchain_core.language_models import BaseChatModel

from agent.deep_agent import AgentBudgets, CuesDeepAgent, create_cues_deep_agent
from agent.progress_history import ProgressHistoryStore
from agent.prompt_history import PromptHistoryStore
from agent.supabase_teacher_review import SupabaseTeacherReviewStore
from agent.teacher_review import TeacherReviewStorage, TeacherReviewStore
from shared.supabase_client import REPO_ROOT, get_client

log = logging.getLogger(__name__)


class RuntimePersistenceError(RuntimeError):
    """Persistence was configured but cannot be initialized; never fall back."""


def review_store_from_env(
    *, offline: bool = False, env_file: Path | None = None
) -> TeacherReviewStorage:
    """Resolve backend credentials locally; never put config into model context.

    Nonempty process env wins. Root .env wins over web/.env.local fallback.
    An explicit env_file replaces default file discovery (useful for deployment
    and isolated tests). It does not override process environment variables.
    """
    if offline:
        log.info("Teacher review storage: memory (explicit offline mode)")
        return TeacherReviewStore()
    if env_file is not None:
        if not env_file.is_file():
            raise RuntimePersistenceError("The configured backend env file does not exist.")
        config = dict(dotenv_values(env_file))
    else:
        config = dict(dotenv_values(REPO_ROOT / "web/.env.local"))
        config.update(
            {
                k: v
                for k, v in dotenv_values(REPO_ROOT / ".env").items()
                if v is not None and v.strip()
            }
        )
    # Empty template values loaded by the compatibility client must not erase
    # a valid local fallback. Use offline=True to intentionally disable storage.
    config.update({k: v for k, v in os.environ.items() if v.strip()})
    url = (config.get("SUPABASE_URL") or "").strip()
    key = (config.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url and not key:
        # A frontend public URL alone is not backend persistence configuration.
        log.info("Teacher review storage: memory (no backend Supabase credentials)")
        return TeacherReviewStore()
    url = url or (config.get("NEXT_PUBLIC_SUPABASE_URL") or "").strip()
    if not url or not key:
        raise RuntimePersistenceError(
            "Incomplete review persistence configuration: provide SUPABASE_URL "
            "and SUPABASE_SERVICE_ROLE_KEY (NEXT_PUBLIC_SUPABASE_URL may supply the URL)."
        )
    try:
        client = get_client(url, key)
        if client is None:
            raise RuntimeError("Client unavailable")
        # Authenticate and check migration/table availability without reading
        # student context or writing a startup probe record.
        client.table("teacher_reviews").select("id").limit(1).execute()
    except Exception:
        raise RuntimePersistenceError(
            "Could not initialize Supabase teacher-review persistence; check backend "
            "credentials, connectivity, and migration 003. No in-memory fallback was used."
        ) from None
    log.info("Teacher review storage: Supabase")
    return SupabaseTeacherReviewStore(client)


def create_runtime_agent(
    model: BaseChatModel,
    history: ProgressHistoryStore,
    *,
    prompt_history: PromptHistoryStore | None = None,
    budgets: AgentBudgets | None = None,
    offline: bool = False,
    env_file: Path | None = None,
) -> CuesDeepAgent:
    """Provider-independent runtime construction; core tools receive a store only."""
    reviews = review_store_from_env(offline=offline, env_file=env_file)
    return create_cues_deep_agent(
        model,
        history,
        prompt_history=prompt_history,
        budgets=budgets if budgets is not None else AgentBudgets(),
        reviews=reviews,
    )
