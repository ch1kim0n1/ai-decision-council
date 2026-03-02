"""Typed schema objects shared across package modules."""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ModelRunError:
    """Structured per-model error payload for partial-failure runs."""

    model: str
    stage: str
    error_code: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "model": self.model,
            "stage": self.stage,
            "error_code": self.error_code,
            "message": self.message,
        }


@dataclass
class CouncilResult:
    """Structured council output for application integrations."""

    stage1: List[Dict[str, Any]]
    stage2: List[Dict[str, Any]]
    stage3: Dict[str, Any]
    metadata: Dict[str, Any]
    errors: List[ModelRunError] = field(default_factory=list)

    @property
    def final_response(self) -> str:
        """Final synthesized response text."""
        return self.stage3.get("response", "")

    @property
    def final_model(self) -> str:
        """Model identifier that produced the final response."""
        return self.stage3.get("model", "")

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to serializable dictionary."""
        return {
            "stage1": self.stage1,
            "stage2": self.stage2,
            "stage3": self.stage3,
            "metadata": self.metadata,
            "errors": [err.to_dict() for err in self.errors],
        }
