"""
Some demo code to create patients and encounters in the database.
"""

from typing import Any, Dict

from amt_nano.db.surreal import DbController

from lib.migrations.demo_utils import (
    EncounterFactory,
    PatientFactory,
    select_n_random_rows_from_csv,
)
from lib.models.patient.main import store_encounter, store_patient
from settings import logger


def create_n_patients(n: int = 5) -> None:
    """
    Create a number of patients with encounters and diagnostic codes.
    :param n: Number of patients to create.
    :return: None
    """
    db = DbController(namespace="arsmedicatech", database="patients")

    path = r"section111validicd10-jan2025_0_sample.csv"
    for _ in range(n):
        patient = PatientFactory(
            factory_class=None
        )  # Replace None with the appropriate class if needed

        encounter = EncounterFactory(
            factory_class=None
        )  # Replace None with the appropriate class if needed
        encounter.diagnostic_codes = select_n_random_rows_from_csv(path, 3)  # type: ignore

        logger.debug(
            patient.first_name,
            patient.last_name,
            patient.date_of_birth,
            patient.phone,
            patient.sex,
            patient.email,
        )

        result: Dict[str, Any] = store_patient(db, patient)  # type: ignore

        result = result["result"][0]
        patient_id = str(result.get("id", ""))

        store_encounter(db, encounter, patient_id)  # type: ignore

    db.close()


# create_schema()
# create_n_patients(5)


def create_forms() -> None:
    """
    Create a demo form structure and a sample form submission.
    :return: None
    """
    # document store for forms of arbitrary structure...
    db = DbController(namespace="arsmedicatech", database="patients")
    db.connect()

    patient_registration_form_structure: Dict[str, Any] = {
        "form_name": "Patient Registration",
        "form_fields": [
            {
                "field_id": "first_name",
                "field_name": "First Name",
                "field_type": "text",
                "required": True,
            },
            {
                "field_id": "last_name",
                "field_name": "Last Name",
                "field_type": "text",
                "required": True,
            },
            {
                "field_id": "date_of_birth",
                "field_name": "Date of Birth",
                "field_type": "date",
                "required": True,
            },
            {
                "field_id": "phone",
                "field_name": "Phone",
                "field_type": "phone",
                "required": True,
            },
        ],
    }

    print(
        "Creating patient registration form structure...",
        patient_registration_form_structure,
    )

    patient_registration_form: Dict[str, Any] = {
        "form_name": "patient_registration",
        "form_data": {
            "first_name": "Richard",
            "last_name": "Roe",
            "date_of_birth": "1980-01-01",
            "phone": "123-456-7890",
        },
    }

    result = db.create("forms", patient_registration_form)
    logger.debug(str(result))


if __name__ == "__main__":
    # Uncomment to create patients and encounters
    # create_n_patients(5)

    # Uncomment to create forms
    # create_forms()
    ...
