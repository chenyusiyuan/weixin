"""FastAPI application entry point and component assembly."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Ensure project root is in sys.path for tools.* imports
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fin_copilot.agents.compliant_generator import CompliantGenerator
from fin_copilot.agents.confidence_auditor import ConfidenceAuditor
from fin_copilot.agents.longtail_reasoner import LongtailReasoner
from fin_copilot.compliance.rule_checker import RuleComplianceChecker
from fin_copilot.config import Settings, get_settings
from fin_copilot.context.context_manager import ContextManager
from fin_copilot.demo.store import get_demo_store
from fin_copilot.knowledge.value_added import ValueAddedKnowledgeRetriever
from fin_copilot.llm.client import LLMClient
from fin_copilot.llm.profiles import load_llm_profiles
from fin_copilot.orchestrator import Orchestrator
from fin_copilot.routers.demo import router as demo_router
from fin_copilot.routers.gateway import router, set_llm_client, set_orchestrator
from fin_copilot.routing.domain_classifier import DomainClassifier
from fin_copilot.routing.embedding_domain_classifier import EmbeddingDomainClassifier
from fin_copilot.routing.rule_engine import RuleEngine
from fin_copilot.routing.skill_embedding_index import SkillEmbeddingIndex
from fin_copilot.routing.skill_router import SkillRouter
from fin_copilot.skills.loader import SkillLoader

logger = logging.getLogger(__name__)


def build_orchestrator(settings: Settings) -> tuple[Orchestrator, LLMClient]:
    """Wire all components together and return (orchestrator, llm_client)."""
    skill_loader = SkillLoader(
        str(settings.resolve_path(settings.SKILL_DEFINITIONS_DIR)),
        str(settings.resolve_path(settings.SKILL_REGISTRY_PATH)),
    )
    context_mgr = ContextManager(settings)
    rule_engine = RuleEngine(
        str(settings.resolve_path(settings.RULE_ENGINE_PATH)),
        skill_loader,
    )
    domain_classifier = DomainClassifier()
    skill_embedding_index = None
    if settings.ENABLE_HYBRID_SKILL_RECALL:
        try:
            domain_classifier = EmbeddingDomainClassifier(
                api_url=settings.EMBED_API_URL,
                model=settings.EMBED_MODEL,
                timeout=settings.LLM_TIMEOUT,
            )
        except Exception as exc:
            logger.warning(
                "hybrid recall disabled: failed to build embedding domain classifier: %s",
                exc,
            )
        else:
            try:
                skill_embedding_index = SkillEmbeddingIndex(
                    skill_loader,
                    api_url=settings.EMBED_API_URL,
                    model=settings.EMBED_MODEL,
                    timeout=settings.LLM_TIMEOUT,
                )
            except Exception as exc:
                logger.warning(
                    "skill-cos recall disabled: failed to build skill embedding index: %s",
                    exc,
                )

    llm_profiles, default_llm_profile_id = load_llm_profiles(settings)
    llm_client = LLMClient(
        base_url=settings.LLM_API_URL,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        timeout=settings.LLM_TIMEOUT,
        profiles=llm_profiles,
        default_profile_id=default_llm_profile_id,
    )

    skill_router = SkillRouter(
        llm_client,
        skill_loader,
        str(settings.resolve_path(settings.SKILL_PROMPTS_DIR) / "skill_routing.md"),
    )
    confidence_auditor = ConfidenceAuditor(
        threshold=settings.CONFIDENCE_THRESHOLD,
    )
    compliant_generator = CompliantGenerator(
        llm_client,
        str(settings.resolve_path(settings.SKILL_PROMPTS_DIR) / "compliant_gen.md"),
    )
    compliance_checker = RuleComplianceChecker(
        str(settings.resolve_path(settings.FORBIDDEN_WORDS_PATH)),
        str(settings.resolve_path(settings.KEY_RULES_PATH)),
        str(settings.resolve_path(settings.LONGTAIL_CONSTRAINTS_PATH)),
    )
    longtail_reasoner = LongtailReasoner(
        llm_client=llm_client,
        prompt_path=str(settings.resolve_path(settings.SKILL_PROMPTS_DIR) / "longtail_reasoning.md"),
    )
    value_added_knowledge = None
    if settings.ENABLE_VALUE_ADDED_KNOWLEDGE:
        value_added_knowledge = ValueAddedKnowledgeRetriever(
            settings.PROJECT_ROOT,
            services_path=settings.VALUE_ADDED_SERVICES_PATH,
            text_blocks_path=settings.VALUE_ADDED_TEXT_BLOCKS_PATH,
            image_blocks_path=settings.VALUE_ADDED_IMAGE_BLOCKS_PATH,
        )

    orchestrator = Orchestrator(
        context_mgr=context_mgr,
        rule_engine=rule_engine,
        domain_classifier=domain_classifier,
        skill_router=skill_router,
        skill_loader=skill_loader,
        skill_embedding_index=skill_embedding_index,
        confidence_auditor=confidence_auditor,
        compliant_generator=compliant_generator,
        compliance_checker=compliance_checker,
        longtail_reasoner=longtail_reasoner,
        value_added_knowledge=value_added_knowledge,
        settings=settings,
    )
    return orchestrator, llm_client


_llm_client: LLMClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _llm_client
    settings = get_settings()
    get_demo_store()
    orchestrator, _llm_client = build_orchestrator(settings)
    set_orchestrator(orchestrator)
    set_llm_client(_llm_client)
    yield
    if _llm_client:
        await _llm_client.close()
    set_llm_client(None)


app = FastAPI(
    title="Financial Copilot",
    description="金融客服坐席话术推荐系统",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(demo_router)

_demo_static_dir = _project_root / "static" / "demo"
app.mount("/demo-assets", StaticFiles(directory=str(_demo_static_dir)), name="demo-assets")


@app.get("/demo", include_in_schema=False)
async def demo_workspace():
    return FileResponse(_demo_static_dir / "index.html")
