"""
Common definitions for Patient and Encounter models in SurrealDB.
"""

from typing import Any, Dict, List

PatientDict = Dict[
    str, str | int | List[Any] | None
]  # Define a type for patient dictionaries

EncounterDict = Dict[
    str, str | int | List[Any] | None
]  # Define a type for encounter dictionaries
