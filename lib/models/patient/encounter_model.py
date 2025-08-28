"""
Encounter Model and SOAPNotes for SurrealDB.
"""

import ast
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from lib.models.patient.common import EncounterDict
from lib.models.patient.patient_model import Patient
from settings import logger
from surrealdb import RecordID  # type: ignore[import-untyped]


class SOAPNotes:
    """
    Represents SOAP notes for an encounter.
    """

    def __init__(
        self, subjective: str, objective: str, assessment: str, plan: str
    ) -> None:
        """
        Initializes a SOAPNotes instance.
        :param subjective: Subjective observations from the patient.
        :param objective: Objective findings from the examination.
        :param assessment: Assessment of the patient's condition.
        :param plan: Plan for treatment or follow-up.
        :return: None
        """
        self.subjective = subjective
        self.objective = objective
        self.assessment = assessment
        self.plan = plan

    def serialize(self) -> Dict[str, Any]:
        """
        Serializes the SOAPNotes instance to a dictionary.
        :return: dict containing the SOAP notes.
        """
        return dict(
            subjective=self.subjective,
            objective=self.objective,
            assessment=self.assessment,
            plan=self.plan,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SOAPNotes":
        """
        Creates a SOAPNotes instance from a dictionary.
        :param data: dict containing SOAP notes fields.
        :return: SOAPNotes instance
        """
        return cls(
            subjective=str(data.get("subjective") or ""),
            objective=str(data.get("objective") or ""),
            assessment=str(data.get("assessment") or ""),
            plan=str(data.get("plan") or ""),
        )


class Encounter:
    """
    Represents an encounter note in the system.
    """

    def __init__(
        self,
        id: str,
        observation_date: datetime,
        provider_id: str,
        note_text: Optional[SOAPNotes | str] = None,
        additional_notes: Optional[str] = None,
        diagnostic_codes: Optional[List[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Initializes an Encounter instance.
        :param id: Unique identifier for the encounter note.
        :param observation_date: Date when the encounter note was created.
        :param provider_id: Unique identifier for the healthcare provider.
        :param note_text: SOAPNotes object containing the structured notes.
        :param additional_notes: Additional notes or comments for the encounter.
        :param diagnostic_codes: List of diagnostic codes associated with the encounter.
        :param metadata: Json of metadata.
        :return: None
        """
        if (
            note_text
            and hasattr(note_text, "serialize")
            and not isinstance(note_text, str)
        ):
            self.note_text = note_text.serialize()  # Store as object, not string
            self.note_type = "soap"
        else:
            self.note_text = self.additional_notes or ""
            self.note_type = "text"

        self.id = id
        self.observation_date = observation_date
        self.provider_id = provider_id
        self.metadata = metadata
        self.additional_notes = additional_notes
        self.diagnostic_codes = diagnostic_codes
        self.status = None  # e.g., locked, signed, etc.

    def __repr__(self) -> str:
        return f"<Encounter id={self.id}, date={self.observation_date}>"

    def to_dict(self) -> Dict[str, Any]:

        return {
            "observation_date": self.observation_date,
            "provider_id": self.provider_id,
            "note_text": self.note_text,
            "note_type": self.note_type,
            "diagnostic_codes": self.diagnostic_codes,
        }

    @classmethod
    def serialize_encounter(cls, encounter: Any) -> EncounterDict:
        """
        Serializes an encounter dictionary to ensure all IDs are strings and handles RecordID types.
        :param encounter: dict - The encounter data to serialize.
        :return: EncounterDict - The serialized encounter data with all IDs as strings.
        """
        # Handle case where encounter is not a dict
        if not isinstance(encounter, dict):
            if hasattr(encounter, "__str__"):
                return cast(
                    EncounterDict,
                    {
                        "id": str(encounter.id),
                        "patient": str(encounter.patient),
                    },
                )
            else:
                return cast(EncounterDict, {})

        # Create a copy to avoid modifying the original
        result: Dict[str, Any] = {}

        # convert encounter['id'] to string...
        for key, value in encounter.items():
            logger.debug("key [encounter]", key, value)
            if isinstance(value, list):
                result[key] = [
                    str(item) if isinstance(item, int) else item for item in value
                ]
            elif isinstance(value, int):
                result[key] = str(value)
            elif key == "patient" and isinstance(value, dict):
                result[key] = Patient.serialize_patient(value)
            elif key == "patient" and isinstance(value, RecordID):
                result[key] = str(value)
            elif key == "id" and isinstance(value, RecordID):
                result[key] = str(value)
            elif key == "note_text" and isinstance(value, str):
                logger.debug(
                    f"Processing note_text: {value[:100]}..."
                )  # Log first 100 chars
                # Check if this is a JSON string or Python dict string that should be parsed as SOAP notes
                try:
                    # First try JSON parsing
                    parsed = json.loads(value)
                    if isinstance(parsed, dict) and all(
                        k in parsed
                        for k in ["subjective", "objective", "assessment", "plan"]
                    ):
                        logger.debug("Successfully parsed as JSON SOAP notes")
                        result[key] = parsed
                        result["note_type"] = "soap"
                        return result
                except (json.JSONDecodeError, TypeError) as e:
                    logger.debug(f"JSON parsing failed: {e}")
                    pass

                # If JSON parsing failed, try Python literal_eval for Python dict strings
                try:
                    parsed = ast.literal_eval(value)
                    if isinstance(parsed, dict) and all(
                        k in parsed
                        for k in ["subjective", "objective", "assessment", "plan"]
                    ):
                        logger.debug("Successfully parsed as Python dict SOAP notes")
                        result[key] = parsed
                        result["note_type"] = "soap"
                    else:
                        logger.debug("Parsed as dict but not SOAP notes")
                        result[key] = value
                except (ValueError, SyntaxError, TypeError) as e:
                    logger.debug(f"Python literal_eval failed: {e}")
                    result[key] = value
            else:
                result[key] = value
        return cast(EncounterDict, result)

    @classmethod
    def schema(cls) -> str:
        """
        Defines the schema for the Encounter table in SurrealDB.
        :return: The entire schema definition for the table in a single string containing all statements.
        """
        return """
            DEFINE TABLE encounter SCHEMAFULL;
            DEFINE FIELD note_id on encounter TYPE option<record> VALUE id;
            DEFINE FIELD patient ON encounter TYPE record<patient>;
            DEFINE FIELD provider_id ON encounter TYPE record<provider>;
            DEFINE FIELD note_text ON encounter FLEXIBLE TYPE string | object;
            DEFINE FIELD note_type ON encounter TYPE "text" | "soap";
            DEFINE FIELD diagnostic_codes ON encounter TYPE array<string>;
            DEFINE FIELD update_date ON encounter TYPE datetime;
            DEFINE FIELD observation_date ON encounter TYPE datetime;
            DEFINE FIELD metadata on encounter TYPE object;
            DEFINE FIELD created_at ON encounter TYPE datetime VALUE time::now() READONLY;
            DEFINE FIELD updated_at ON encounter TYPE datetime VALUE time::now();
            DEFINE ANALYZER medical_text_analyzer TOKENIZERS class FILTERS lowercase, ascii;
            DEFINE INDEX idx_encounter_notes ON TABLE encounter FIELDS note_text SEARCH ANALYZER medical_text_analyzer BM25 HIGHLIGHTS;
            DEFINE INDEX idx_encounter_note_id ON encounter FIELDS note_id UNIQUE;
        """
