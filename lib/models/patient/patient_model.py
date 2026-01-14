"""
Patient Model for SurrealDB.
"""

from typing import Any, Dict, List, Optional, Tuple, cast

from lib.models.patient.common import PatientDict
from settings import logger


class Patient:
    """
    Represents a patient in the system.
    """

    def __init__(
        self,
        demographic_no: str,
        organization_id: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        year_of_birth: Optional[str] = None,  # TODO: add validation for these three
        month_of_birth: Optional[str] = None,
        date_of_birth: Optional[str] = None,
        location: Optional[Tuple[str, str, str, str]] = None,
        sex: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> None:
        """
        Initializes a Patient instance.
        :param demographic_no: Unique identifier for the patient.
        :param first_name: Patient's first name.
        :param last_name: Patient's last name.
        :param year_of_birth: Patient's date of birth YYYY.
        :param month_of_birth: Patient's date of birth MM.
        :param date_of_birth: Patient's date of birth DD.
        :param location: Tuple containing (city, province, country, postal code).
        :param sex: Patient's sex (F, M, O)
        :param phone: Patient's phone number.
        :param email: Patient's email address.
        """
        self.demographic_no = demographic_no
        self.organization_id = organization_id
        self.first_name = first_name
        self.last_name = last_name
        self.year_of_birth = year_of_birth
        self.month_of_birth = month_of_birth
        self.date_of_birth = date_of_birth
        self.location = location
        self.sex = sex
        self.phone = phone
        self.email = email

        self.alerts: List[Any] = []
        self.ext_attributes: Dict[str, Any] = {}  # For demographicExt key-value pairs
        self.encounters: List[Any] = []  # List of Encounter objects
        self.cpp_issues: List[Any] = []  # Summaries from casemgmt_cpp or casemgmt_issue
        self.ticklers: List[Any] = []  # Tickler (reminders/follow-up tasks)

    def __repr__(self) -> str:
        return (
            f"<Patient: {self.first_name} {self.last_name} (ID: {self.demographic_no})>"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "demographic_no": self.demographic_no,
            "organization_id": self.organization_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "year_of_birth": self.date_of_birth,
            "month_of_birth": self.date_of_birth,
            "date_of_birth": self.date_of_birth,
            "location": list(self.location) if self.location is not None else [],
            "sex": self.sex,
            "phone": self.phone,
            "email": self.email,
            # location could be stored as a separate field or nested object up to you.
        }

    # TODO: This is still not working 100%.
    # Let's write some unit tests to find other edge cases.
    @classmethod
    def serialize_patient(cls, patient: Any) -> PatientDict:
        """
        Serializes a patient dictionary to ensure all IDs are strings and handles RecordID types.
        :param patient: dict - The patient data to serialize.
        :return: PatientDict - The serialized patient data with all IDs as strings.
        """
        # Handle case where patient is not a dict
        if not isinstance(patient, dict):
            if hasattr(patient, "__str__"):
                return cast(PatientDict, {"demographic_no": str(patient)})
            else:
                return cast(PatientDict, {})

        # Create a copy to avoid modifying the original
        result: Dict[str, Any] = {}

        # convert patient['id'] to string...
        for key, value in patient.items():
            logger.debug("key", key, value)
            if isinstance(value, list):
                result[key] = [
                    str(item) if isinstance(item, int) else item for item in value
                ]
            elif isinstance(value, int):
                result[key] = str(value)
            else:
                result[key] = value
        return cast(PatientDict, result)

    @classmethod
    def schema(cls) -> str:
        """
        Defines the schema for the patient table in SurrealDB.
        :return: The entire schema definition for the table in a single string containing all statements.
        """
        return """
            DEFINE TABLE patient SCHEMAFULL;
            DEFINE FIELD demographic_no on patient TYPE option<record> VALUE id;
            DEFINE FIELD organization_id ON patient TYPE record<organization>;
            DEFINE FIELD first_name ON patient TYPE string;
            DEFINE FIELD last_name ON patient TYPE string;
            DEFINE FIELD year_of_birth ON patient TYPE string;
            DEFINE FIELD month_of_birth ON patient TYPE string;
            DEFINE FIELD date_of_birth ON patient TYPE string;
            DEFINE FIELD location ON patient TYPE array;
            DEFINE FIELD sex ON patient TYPE string;
            DEFINE FIELD phone ON patient TYPE string;
            DEFINE FIELD email ON patient TYPE string ASSERT string::is::email($value);
            DEFINE FIELD created_at ON patient TYPE datetime VALUE time::now() READONLY;
            DEFINE FIELD updated_at ON patient TYPE datetime VALUE time::now();
            DEFINE INDEX idx_patient_demographic_no ON patient FIELDS demographic_no UNIQUE;
        """
