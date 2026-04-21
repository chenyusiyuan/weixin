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

    # Compliance
    FORBIDDEN_WORDS_PATH: str = "skills/references/compliance/forbidden_words.json"
    KEY_RULES_PATH: str = "skills/references/compliance/key_rules.json"
    LONGTAIL_CONSTRAINTS_PATH: str = "skills/references/compliance/longtail_constraints.json"

    # Session
    SESSION_TTL_SECONDS: int = 3600

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
