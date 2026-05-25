"""Application configuration via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Paths
    PROJECT_ROOT: str = str(Path(__file__).resolve().parent.parent)

    # LLM
    LLM_API_URL: str = "http://localhost:11434/v1"
    LLM_API_KEY: str = "ollama"
    LLM_MODEL: str = "qwen2.5:7b"
    LLM_PROFILES_PATH: str = "config/llm_profiles.json"

    # Embedding (Chain C only)
    EMBED_API_URL: str = "http://localhost:11434/api/embed"
    EMBED_MODEL: str = "bge-m3"

    # Skill paths (relative to PROJECT_ROOT)
    SKILL_DEFINITIONS_DIR: str = "skills/definitions"
    SKILL_REGISTRY_PATH: str = "skills/registry.json"
    SKILL_PROMPTS_DIR: str = "skills/prompts"

    # Context
    SLIDING_WINDOW_SIZE: int = 8
    SUMMARY_MAX_LENGTH: int = 300
    TOOL_CACHE_TTL: int = 300

    # Routing
    CONFIDENCE_THRESHOLD: float = 0.5
    SKILL_ROUTE_MIN_CONFIDENCE: float = 0.3
    RULE_ENGINE_PATH: str = "rules/rule_engine.json"
    ENABLE_HYBRID_SKILL_RECALL: bool = True
    SKILL_MULTI_DOMAIN_K: int = 3
    SKILL_COS_TOP_M: int = 12
    SKILL_MAX_CANDIDATES: int = 20
    SKILL_CANDIDATE_SOURCE: str = "hybrid"
    PRIOR_SKILL_WEIGHT: float = 0.65
    PRIOR_DOMAIN_WEIGHT: float = 0.25
    PRIOR_KEYWORD_WEIGHT: float = 0.10
    ENABLE_VALUE_ADDED_KNOWLEDGE: bool = True
    VALUE_ADDED_SERVICES_PATH: str = "sop/structured/value_added_text/services.json"
    VALUE_ADDED_TEXT_BLOCKS_PATH: str = "sop/structured/value_added_text/text_blocks.jsonl"
    VALUE_ADDED_IMAGE_BLOCKS_PATH: str = "sop/structured/value_added_images/image_blocks.jsonl"

    # Compliance
    FORBIDDEN_WORDS_PATH: str = "skills/references/compliance/forbidden_words.json"
    KEY_RULES_PATH: str = "skills/references/compliance/key_rules.json"
    LONGTAIL_CONSTRAINTS_PATH: str = "skills/references/compliance/longtail_constraints.json"

    # Session
    SESSION_TTL_SECONDS: int = 3600
    DEMO_DB_PATH: str = "demo_data/demo.sqlite3"

    # Multi-turn / dialogue state
    ENABLE_INTENT_STICKY: bool = True
    STICKY_MAX_TURNS: int = 3
    STICKY_FOLLOWUP_MAX_LEN: int = 12
    DUPLICATE_REPLY_THRESHOLD: float = 0.82
    ENABLE_REFERENCE_RESOLUTION: bool = True

    # LLM generation params
    ROUTING_TEMPERATURE: float = 0.1
    GENERATION_TEMPERATURE: float = 0.3
    LLM_TIMEOUT: float = 30.0

    model_config = {"env_file": ".env", "extra": "ignore"}

    def resolve_path(self, relative: str) -> Path:
        """Convert a project-relative path to an absolute path."""
        return Path(self.PROJECT_ROOT) / relative


@lru_cache
def get_settings() -> Settings:
    return Settings()
