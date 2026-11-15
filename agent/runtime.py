"""Backend composition: select review persistence, then inject it into the agent."""

import logging
import os
from pathlib import Path

from dotenv import dotenv_values
from langchain_core.language_models import BaseChatModel

from agent.deep_agent import AgentBudgets, CuesDeepAgent, create_cues_deep_agent
from agent.notifications import ReviewNotifier, spectrum_env, spectrum_notifier
from agent.progress_history import ProgressHistoryStore
from agent.prompt_history import PromptHistoryStore
from agent.seat_state_runtime import (
    SeatStatePipeline,
    SeatStateRuntime,
    SeatStateSource,
    SupabaseSeatStateSource,
)
from agent.supabase_teacher_review import SupabaseTeacherReviewStore
from agent.teacher_review import TeacherReviewStorage, TeacherReviewStore
from shared.contracts import Activity
from shared.supabase_client import REPO_ROOT, get_client

log = logging.getLogger(__name__)


class RuntimePersistenceError(RuntimeError):
    """Persistence was configured but cannot be initialized; never fall back."""


def review_store_from_env(
    *, offline: bool = False, env_file: Path | None = None, notifier: ReviewNotifier | None = None
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
        # Photon/Spectrum is its own nested SDK project. Only its backend
        # configuration is imported here; none of these values enter model or
        # frontend context.
        config.update(
            {
                k: v
                for k, v in dotenv_values(REPO_ROOT / "cues/.env").items()
                if (k.startswith("SPECTRUM_") or k == "CUES_USE_STATIC_TEACHER_PHONE")
                and v is not None
                and v.strip()
            }
        )
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
    if notifier is None:
        # Default discovery re-reads cues/.env on each send (credentials saved after
        # startup work without a restart). An explicit env_file is used as given.
        notifier = spectrum_notifier(
            config,
            REPO_ROOT,
            client=client,
            reread_env=REPO_ROOT / "cues/.env" if env_file is None else None,
            pinned=spectrum_env() if env_file is None else None,
        )
    return SupabaseTeacherReviewStore(client, notifier=notifier)


def create_runtime_agent(
    model: BaseChatModel,
    history: ProgressHistoryStore,
    *,
    prompt_history: PromptHistoryStore | None = None,
    budgets: AgentBudgets | None = None,
    offline: bool = False,
    env_file: Path | None = None,
    notifier: ReviewNotifier | None = None,
) -> CuesDeepAgent:
    """Provider-independent runtime construction; core tools receive a store only."""
    reviews = review_store_from_env(offline=offline, env_file=env_file, notifier=notifier)
    return create_cues_deep_agent(
        model,
        history,
        prompt_history=prompt_history,
        budgets=budgets if budgets is not None else AgentBudgets(),
        reviews=reviews,
    )


def create_seat_state_runtime(
    model: BaseChatModel,
    activities: list[Activity],
    *,
    history: ProgressHistoryStore | None = None,
    prompt_history: PromptHistoryStore | None = None,
    budgets: AgentBudgets | None = None,
    offline: bool = False,
    env_file: Path | None = None,
    notifier: ReviewNotifier | None = None,
    source: SeatStateSource | None = None,
    progress_window_seconds: float = 4,
    escalation_config=None,
    poll_seconds: float = 1.0,
    publish_progress: bool = False,
) -> SeatStateRuntime:
    """Build the continuous SeatState path using explicit, replaceable dependencies.

    A supplied source supports offline tests/development. Without one, persistent
    review configuration is required and its authenticated client is reused for
    seat_state polling; a configured live runtime never silently reads locally.
    """
    from agent.escalation import DEFAULT_ESCALATION_CONFIG

    progress_history = history if history is not None else ProgressHistoryStore()
    agent = create_runtime_agent(
        model,
        progress_history,
        prompt_history=prompt_history,
        budgets=budgets,
        offline=offline,
        env_file=env_file,
        notifier=notifier,
    )
    if source is None:
        if not isinstance(agent.reviews, SupabaseTeacherReviewStore):
            raise RuntimePersistenceError(
                "Continuous SeatState runtime requires backend Supabase configuration "
                "or an explicitly injected source."
            )
        from agent.seat_state_runtime import local_station

        source = SupabaseSeatStateSource(agent.reviews.client, station_provider=local_station)
    from agent.live_progress import SupabaseProgressPublisher

    pipeline = SeatStatePipeline(
        activities,
        agent,
        progress_history,
        publisher=(
            SupabaseProgressPublisher(agent.reviews.client)
            if publish_progress and isinstance(agent.reviews, SupabaseTeacherReviewStore)
            else None
        ),
        progress_window_seconds=progress_window_seconds,
        escalation_config=(
            DEFAULT_ESCALATION_CONFIG if escalation_config is None else escalation_config
        ),
    )
    return SeatStateRuntime(source, pipeline, poll_seconds=poll_seconds)
