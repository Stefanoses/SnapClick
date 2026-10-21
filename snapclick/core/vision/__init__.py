"""Wizja komputerowa: dopasowywanie szablonów i ich rejestr."""

from .matcher import MatchResult, find_template
from .templates import TemplateRegistry

__all__ = ["MatchResult", "find_template", "TemplateRegistry"]
