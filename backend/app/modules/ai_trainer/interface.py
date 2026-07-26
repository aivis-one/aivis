# =============================================================================
# AIVIS.ONE Backend -- AI Trainer Interface (Sprint 10.1)
# =============================================================================
#
# Stub protocol for future agent certification quiz.
#
# AITrainerProtocol:
#   Adaptive quiz qualifying a user for the agent role. In MVP,
#   agent applications are submitted without a quiz and decided
#   manually by Staff. Phase 2: quiz before application, result
#   attached to AgentApplication.
#
# Stub types:
#   TrainingQuestion -- single quiz question generated for an agent.
#   EvaluationResult -- result of evaluating an agent's answer.
# =============================================================================

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class TrainingQuestion:
    """Single quiz question for agent certification (stub)."""

    question_id: UUID
    agent_id: UUID
    topic: str
    text: str


@dataclass(frozen=True)
class EvaluationResult:
    """Result of evaluating an agent's answer (stub)."""

    question_id: UUID
    is_correct: bool
    feedback: str


class AITrainerProtocol(Protocol):
    """Public interface for the AI trainer module.

    Adaptive quiz for agent qualification. Implementation
    deferred to Phase 2.
    """

    async def generate_question(
        self, agent_id: UUID, topic: str
    ) -> TrainingQuestion: ...

    async def evaluate_answer(
        self, question_id: UUID, answer: str
    ) -> EvaluationResult: ...
