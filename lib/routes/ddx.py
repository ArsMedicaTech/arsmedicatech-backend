"""
Routes for differential diagnosis (ddx) related endpoints.
"""

from typing import Any, Dict, List


class DDXContext:
    def __init__(self, prompt: str, details: Dict[str, Any]):
        self.prompt = prompt
        self.details = details

    def to_json(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "details": self.details,
        }


class DDXSuggestion:
    def __init__(self, name: str, rationale: str, confidence_score: float):
        self.name = name
        self.rationale = rationale
        self.confidence_score = confidence_score

    @classmethod
    def from_json(cls, json: Dict[str, Any]) -> "DDXSuggestion":
        return cls(
            name=json.get("name", ""),
            rationale=json.get("rationale", ""),
            confidence_score=float(json.get("confidence_score", 0.0)),
        )

    def to_json(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "rationale": self.rationale,
            "confidence_score": self.confidence_score,
        }


def suggest_ddx(context: DDXContext, n_suggestions: int) -> List[DDXSuggestion]:
    """
    Mock function to simulate fetching a differential diagnosis suggestion
    from an API based on the provided context.
    """
    # In a real implementation, this function would make an HTTP request to the DDX API.
    # Here, we return a mock suggestion for demonstration purposes.
    result = []

    for i in range(n_suggestions):
        mock_response = {
            "name": f"Diagnosis {i + 1}",
            "rationale": f"This diagnosis is suggested based on the symptoms provided in the prompt: {context.prompt}",
            "confidence_score": 0.8 - (i * 0.1),
        }

        result.append(DDXSuggestion.from_json(mock_response))

    return result
