"""
Encounter Model and SOAPNotes for SurrealDB.
"""

import ast
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, cast

from amt_nano.db.surreal import AsyncDbController, DbController
from surrealdb import RecordID  # type: ignore[import-untyped]

from lib.models.patient import Patient, PatientDict
from settings import logger

EncounterDict = Dict[
    str, str | int | List[Any] | None
]  # Define a type for encounter dictionaries


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
        soap_notes: Optional[SOAPNotes] = None,
        additional_notes: Optional[str] = None,
        diagnostic_codes: Optional[List[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Initializes an Encounter instance.
        :param id: Unique identifier for the encounter note.
        :param observation_date: Date when the encounter note was created.
        :param provider_id: Unique identifier for the healthcare provider.
        :param note_text: Original EMR notes.
        :param soap_notes: SOAPNotes object containing the structured notes.
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
            # TODO: error: Incompatible types in assignment (expression has type "str", variable has type "dict[str, Any]")  [assignment]
            self.note_text = additional_notes or ""  # type: ignore
            self.note_type = "text"

        self.id = id
        self.observation_date = observation_date
        self.provider_id = provider_id
        self.metadata = metadata
        self.soap_notes = soap_notes
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
            "soap_notes": self.soap_notes,
            "additional_notes": self.additional_notes,
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
            DEFINE FIELD soap_notes ON encounter FLEXIBLE TYPE object;
            DEFINE FIELD additional_notes ON encounter FLEXIBLE TYPE string | object;
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


class EncounterController:
    @staticmethod
    def store_encounter(
        db: Union[DbController, AsyncDbController],
        encounter: Encounter,
        patient_id: str,
    ) -> Dict[str, Any]:
        """
        Stores an Encounter instance in SurrealDB as encounter:<note_id>,
        referencing the given patient_id (e.g., 'patient:12345').

        :param db: DbController instance connected to SurrealDB.
        :param encounter: Encounter instance to store.
        :param patient_id: Patient ID in the format 'patient:<demographic_no>'.
        :return: Result of the store operation.
        """
        record_id = f"encounter:{encounter.id}"

        # Handle note_text properly - store SOAP notes as objects, not strings
        note_text: Union[str, Dict[str, Any]] = ""
        note_type: str = "text"

        if encounter.soap_notes and hasattr(encounter.soap_notes, "serialize"):
            note_text = encounter.soap_notes.serialize()  # Store as object, not string
            note_type = "soap"
        else:
            note_text = encounter.additional_notes or ""

        content_data: Dict[str, Any] = {
            "note_id": str(encounter.id),
            "observation_date": str(encounter.observation_date),
            "provider_id": str(encounter.provider_id),
            "note_text": note_text,
            "note_type": note_type,
            "diagnostic_codes": encounter.diagnostic_codes,
        }

        query = f"CREATE {record_id}\n"
        set_query = f"""SET  note_id = $note_id,
                            observation_date = $observation_date,
                            provider_id = $provider_id,
                            note_text = $note_text,
                            note_type = $note_type,
                            diagnostic_codes = $diagnostic_codes,
                            patient = {patient_id}
        """

        params = content_data
        db.connect()
        query += set_query
        result = db.query(query, params)

        logger.debug("resultttt", result)

        # If result is a coroutine, await it
        import asyncio

        if asyncio.iscoroutine(result):
            result = asyncio.run(result)

        # If result is a list, return the first item or an empty dict
        if result:
            return result[0] if len(result) > 0 else {}
        elif isinstance(result, dict):
            return result
        else:
            return {}

    @staticmethod
    def search_patient_history(search_term: str) -> List[PatientDict]:
        """
        Performs a full-text search across all encounter notes.

        :param search_term: The term to search for in the encounter notes.
        :return: List of Encounter objects that match the search term.
        """
        db = DbController()
        db.connect()

        logger.debug("ATTEMPTING SEARCH", search_term)

        # This query searches the 'note_text' field.
        # @0@ is a predicate that links to search::score(0) and search::highlight(0).
        # We fetch the score, the highlighted note text, and the associated patient record.
        query = """
            SELECT
                search::score(0) AS score,
                search::highlight('<b>', '</b>', 0) AS highlighted_note,
                patient.*,
                *
            FROM encounter
            WHERE note_text @0@ $query
            ORDER BY score DESC
            LIMIT 15;
        """
        params = {"query": search_term}

        try:
            results = db.query(query, params)
            # Assuming the first result list from the multi-statement response is what we need.
            if results and len(results) > 0:
                logger.debug("SEARCH RESULTS", results)
                serialized_results: List[PatientDict] = []
                for e in results:
                    result = Encounter.serialize_encounter(e)
                    serialized_results.append(result)
                return serialized_results
            return []
        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []
        finally:
            db.close()

    @staticmethod
    def search_encounter_history(search_term: str) -> List[EncounterDict]:
        """
        Performs a full-text search across all encounter notes.

        :param search_term: The term to search for in the encounter notes.
        :return: List of Encounter objects that match the search term.
        """
        db = DbController()
        db.connect()

        logger.debug("ATTEMPTING SEARCH", search_term)

        query = """
            SELECT
                search::score(0) AS score,
                search::highlight('<b>', '</b>', 0) AS highlighted_note,
                patient.*,
                *
            FROM encounter
            WHERE note_text @0@ $query
            ORDER BY score DESC
            LIMIT 15;
        """
        params = {"query": search_term}

        try:
            results = db.query(query, params)
            if results and len(results) > 0:
                logger.debug("SEARCH RESULTS", results)
                serialized_results: List[EncounterDict] = []
                for e in results:
                    result = Encounter.serialize_encounter(e)
                    serialized_results.append(result)
                return serialized_results
            return []
        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []
        finally:
            db.close()

    @staticmethod
    def get_all_encounters() -> List[EncounterDict]:
        """
        Get all encounters from the database

        :return: List of serialized Encounter objects or an empty list if no encounters found.
        """
        db = DbController()
        db.connect()

        try:
            logger.debug("Getting all encounters from database...")
            results = db.select_many("encounter")
            logger.debug(f"Raw encounter results: {results}")

            # Handle different result structures
            if results and len(results) > 0:
                # If the first result has a 'result' key, extract the actual data
                if "result" in results[0]:
                    encounters = results[0]["result"]
                else:
                    encounters = results

                logger.debug(f"Processed encounters: {encounters}")

                if isinstance(encounters, list):
                    serialized_encounters = [
                        Encounter.serialize_encounter(encounter)
                        for encounter in encounters
                    ]
                    logger.debug(f"Serialized encounters: {serialized_encounters}")
                    return serialized_encounters
                else:
                    logger.debug("Encounters is not a list")
                    return []
            else:
                logger.debug("No encounter results or empty results")
                return []
        except Exception as e:
            logger.debug(f"Error getting all encounters: {e}")
            return []
        finally:
            db.close()

    @staticmethod
    def get_encounter_by_id(encounter_id: str) -> EncounterDict:
        """
        Get an encounter by its note_id

        :param encounter_id: The note_id of the encounter to retrieve.
        :return: Serialized encounter data or empty dict if not found.
        """
        logger.debug(f"Getting encounter by ID: {encounter_id}")
        db = DbController()
        db.connect()

        try:
            query = "SELECT * FROM encounter WHERE note_id = $encounter_id"
            params = {"encounter_id": encounter_id}

            logger.debug(f"Executing encounter query: {query} with params: {params}")
            result = db.query(query, params)
            logger.debug(f"Encounter query result: {result}")

            # Handle the result structure
            if result and isinstance(result, list) and len(result) > 0:
                encounter_data = result[0]
                if isinstance(encounter_data, dict) and "result" in encounter_data:
                    encounter_data = cast(
                        Dict[str, Any],
                        (
                            encounter_data["result"][0]
                            if encounter_data["result"]
                            else None
                        ),
                    )

                if encounter_data:
                    serialized_result = Encounter.serialize_encounter(encounter_data)
                    logger.debug(f"Serialized encounter result: {serialized_result}")
                    return serialized_result
                else:
                    logger.debug("No encounter found in query result")
                    return cast(EncounterDict, {})
            else:
                logger.debug("No encounter found")
                return cast(EncounterDict, {})
        except Exception as e:
            logger.debug(f"Error getting encounter: {e}")
            return cast(EncounterDict, {})
        finally:
            db.close()

    @staticmethod
    def get_encounters_by_patient(patient_id: str) -> List[EncounterDict]:
        """
        Get all encounters for a specific patient

        :param patient_id: The demographic_no of the patient to retrieve encounters for.
        :return: List of serialized Encounter objects or an empty list if no encounters found.
        """
        logger.debug(f"Getting encounters for patient: {patient_id}")
        db = DbController()
        db.connect()

        try:
            query = "SELECT * FROM encounter WHERE patient.demographic_no = $patient_id ORDER BY date_created DESC"
            params = {"patient_id": patient_id}

            logger.debug(f"Executing query: {query} with params: {params}")
            result = db.query(query, params)
            logger.debug(f"Query result: {result}")

            # Handle the result structure
            if result and len(result) > 0:
                encounters_data = result[0]
                if "result" in encounters_data:
                    encounters = encounters_data["result"]
                else:
                    encounters = result

                if isinstance(encounters, list):
                    serialized_encounters = [
                        Encounter.serialize_encounter(encounter)
                        for encounter in encounters
                    ]
                    logger.debug(
                        f"Found {len(serialized_encounters)} encounters for patient {patient_id}"
                    )
                    return serialized_encounters
                else:
                    logger.debug("Encounters is not a list")
                    return []
            else:
                logger.debug("No encounters found for patient")
                return []
        except Exception as e:
            logger.debug(f"Error getting patient encounters: {e}")
            return []
        finally:
            db.close()

    @staticmethod
    def create_encounter(
        encounter_data: Dict[str, Any], patient_id: str
    ) -> EncounterDict:
        """
        Create a new encounter record

        :param encounter_data: A dictionary containing encounter information.
        :param patient_id: The demographic_no of the patient to associate with the encounter.
        :return: Serialized encounter data or empty dict if creation failed.
        """
        logger.debug(f"Creating encounter with data: {encounter_data}")
        db = DbController()
        db.connect()

        try:
            # Generate a new note_id if not provided
            if not encounter_data.get("note_id"):
                logger.debug("No note_id provided, generating new one...")
                results = db.select_many("encounter")
                if results and len(results) > 0:
                    existing_ids = [
                        int(e.get("note_id", 0)) for e in results if e.get("note_id")
                    ]
                    new_id = max(existing_ids) + 1 if existing_ids else 1000
                else:
                    new_id = 1000
                encounter_data["note_id"] = str(new_id)
                logger.debug(f"Generated note_id: {new_id}")

            # Handle SOAP notes vs plain text
            note_text = encounter_data.get("note_text")
            soap_notes = None
            additional_notes = ""

            if isinstance(note_text, dict) and all(
                k in note_text
                for k in ["subjective", "objective", "assessment", "plan"]
            ):
                # This is SOAP notes
                note_text_dict: Dict[str, Any] = note_text  # type: ignore
                soap_notes = SOAPNotes(
                    subjective=str(note_text_dict.get("subjective", "")),
                    objective=str(note_text_dict.get("objective", "")),
                    assessment=str(note_text_dict.get("assessment", "")),
                    plan=str(note_text_dict.get("plan", "")),
                )
            else:
                # This is plain text
                additional_notes = note_text if isinstance(note_text, str) else ""

            # Ensure observation_date is a datetime object
            from datetime import datetime

            obs_date = encounter_data.get("observation_date")
            if isinstance(obs_date, str):
                try:
                    observation_date = datetime.fromisoformat(obs_date)
                except Exception:
                    observation_date = datetime.now()
            elif isinstance(obs_date, datetime):
                observation_date = obs_date
            else:
                observation_date = datetime.now()

            # Create Encounter object
            encounter = Encounter(
                id=encounter_data["id"],
                observation_date=observation_date,
                provider_id=str(encounter_data.get("provider_id") or ""),
                note_text=str(encounter_data.get("note_text") or ""),
                soap_notes=soap_notes,
                additional_notes=additional_notes,
                diagnostic_codes=encounter_data.get("diagnostic_codes", []),
            )

            logger.debug(f"Created Encounter object: {encounter}")
            result = EncounterController.store_encounter(
                db, encounter, f"patient:{patient_id}"
            )
            logger.debug(f"Store encounter result: {result}")

            # Handle different result structures
            if result and isinstance(result, list) and len(result) > 0:
                first_result = result[0]
                if isinstance(first_result, dict) and "result" in first_result:
                    final_result = Encounter.serialize_encounter(first_result["result"])
                else:
                    final_result = Encounter.serialize_encounter(first_result)
            elif result:
                final_result = Encounter.serialize_encounter(result)
            else:
                final_result = cast(EncounterDict, {})

            logger.debug(f"Final encounter result: {final_result}")
            return final_result
        except Exception as e:
            logger.debug(f"Error creating encounter: {e}")
            return cast(EncounterDict, {})
        finally:
            db.close()

    @staticmethod
    def update_encounter(
        encounter_id: str, encounter_data: Dict[str, Any]
    ) -> EncounterDict:
        """
        Update an encounter record with only the provided fields

        :param encounter_id: The note_id of the encounter to update.
        :param encounter_data: A dictionary containing the fields to update.
        :return: Serialized updated encounter data or empty dict if not found or no valid fields to update.
        """
        logger.debug(f"Updating encounter with ID: {encounter_id}")
        db = DbController()
        db.connect()

        try:
            # List of valid encounter fields
            valid_fields = {
                "date_created",
                "provider_id",
                "note_text",
                "note_type",
                "diagnostic_codes",
                "status",
            }

            # Only include fields present in encounter_data and valid for the encounter
            update_data = {
                k: v
                for k, v in encounter_data.items()
                if k in valid_fields and v is not None
            }

            if not update_data:
                logger.debug("No valid fields to update for encounter.")
                return cast(EncounterDict, {})

            set_clause = ", ".join([f"{k} = ${k}" for k in update_data.keys()])
            query = f"UPDATE encounter SET {set_clause} WHERE note_id = $encounter_id RETURN *"
            params: Dict[str, Any] = {**update_data, "encounter_id": encounter_id}

            logger.debug(
                f"Executing encounter update query: {query} with params: {params}"
            )
            result = db.query(query, params)
            logger.debug(f"Encounter update result: {result}")

            # Handle the result structure
            if result and len(result) > 0:
                encounter_data = result[0]
                if "result" in encounter_data:
                    encounter_data = cast(
                        Dict[str, Any],
                        (
                            encounter_data["result"][0]
                            if encounter_data["result"]
                            else None
                        ),
                    )

                if encounter_data:
                    serialized_result = Encounter.serialize_encounter(encounter_data)
                    logger.debug(
                        f"Serialized encounter update result: {serialized_result}"
                    )
                    return serialized_result
                else:
                    logger.debug("No encounter found in update result")
                    return cast(EncounterDict, {})
            else:
                logger.debug("Encounter update failed or no encounter found")
                return cast(EncounterDict, {})
        except Exception as e:
            logger.debug(f"Error updating encounter: {e}")
            return cast(EncounterDict, {})
        finally:
            db.close()

    @staticmethod
    def delete_encounter(encounter_id: str) -> bool:
        """
        Delete an encounter record

        :param encounter_id: The note_id of the encounter to delete.
        :return: True if the encounter was deleted, False if not found or deletion failed, None if an error occurred.
        """
        logger.debug(f"Deleting encounter with ID: {encounter_id}")
        db = DbController()
        db.connect()

        try:
            query = "DELETE FROM encounter WHERE note_id = $encounter_id"
            params = {"encounter_id": encounter_id}

            logger.debug(
                f"Executing encounter delete query: {query} with params: {params}"
            )
            result = db.query(query, params)
            logger.debug(f"Encounter delete result: {result}")

            # Check if the delete was successful
            if result and len(result) > 0:
                delete_info = result[0]
                if "result" in delete_info:
                    deleted_count = (
                        len(delete_info["result"]) if delete_info["result"] else 0
                    )
                    logger.debug(f"Deleted {deleted_count} encounter records")
                    return deleted_count > 0
                else:
                    logger.debug("Encounter delete result structure unexpected")
                    return False
            else:
                logger.debug("No encounter delete result")
                return False
        except Exception as e:
            logger.debug(f"Error deleting encounter: {e}")
            return False
        finally:
            db.close()
