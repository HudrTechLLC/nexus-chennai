"""The Nexus agents (spec E3). Every crime-data read goes through Zetaris named queries (R1);
every model call goes through Nightshift on a pinned lane (R2); scores are computed in code (R7)."""

from .alert_writer import AlertWriter, build_alert
from .base import AgentDeps, AgentError, DeadlineExceeded, MemoryStore, Store, parse_model_json
from .extractor import Extractor
from .linker import Candidate, Linker, ScoredPair, hmem_pair
from .planner import Plan, Planner, PlanStep
from .skeptic import Skeptic, SkepticResult
from .tip_guard import TipGuard

__all__ = [
    "AgentDeps", "AgentError", "AlertWriter", "Candidate", "DeadlineExceeded", "Extractor", "Linker",
    "MemoryStore", "Plan", "PlanStep", "Planner", "ScoredPair", "Skeptic", "SkepticResult", "Store", "TipGuard",
    "build_alert", "hmem_pair", "parse_model_json",
]
