"""
Placeholder data generation functions for testing purposes
"""

from typing import Union

from amt_nano.db.surreal import AsyncDbController, DbController
from lib.models.patient.encounter_crud import store_encounter
from lib.models.patient.patient_crud import store_patient

from lib.models.encounter import Encounter
from lib.models.patient import Patient


def add_some_placeholder_encounters(
    db: Union[DbController, AsyncDbController], patient_id: str
) -> None:
    """
    Adds some placeholder encounters for testing purposes.

    :param db: DbController instance connected to SurrealDB.
    :param patient_id: Patient ID in the format 'patient:<demographic_no>'.
    :return: None
    """
    import random
    from datetime import datetime, timedelta

    # Generate 5 random encounters
    for i in range(5):
        note_id = random.randint(100, 999)
        date_created = datetime.now() - timedelta(days=random.randint(1, 30))
        provider_id = f"provider-{random.randint(1, 10)}"
        note_text = f"This is a placeholder note text for encounter {i+1}."
        diagnostic_codes = [f"code-{random.randint(100, 999)}"]

        encounter = Encounter(
            str(note_id),
            date_created,
            provider_id,
            additional_notes=note_text,
            diagnostic_codes=diagnostic_codes,
        )
        store_encounter(db, encounter, patient_id)


def add_some_placeholder_patients(db: Union[DbController, AsyncDbController]) -> None:
    """
    Adds some placeholder patients for testing purposes.
    :param db: DbController instance connected to SurrealDB.
    :return: None
    """
    import random
    from datetime import datetime

    # Generate 5 random patients
    for i in range(5):
        demographic_no = random.randint(100, 999)
        first_name = f"FirstName{i+1}"
        last_name = f"LastName{i+1}"
        date_of_birth = (
            datetime.now()
            .replace(year=datetime.now().year - random.randint(20, 60))
            .isoformat()
        )
        location = (f"City{i+1}", f"State{i+1}", f"Country{i+1}", f"ZipCode{i+1}")
        sex = "r" if random.choice([True, False]) else "m"  # Randomly assign 'r' or 'm'
        phone = f"555-01{i+1:02d}{random.randint(1000, 9999)}"
        email = "patient1@gmail.com"

        patient = Patient(
            demographic_no=str(demographic_no),
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            location=location,
            sex=sex,
            phone=phone,
            email=email,
        )

        # Store the patient in the database
        store_patient(db, patient)

        add_some_placeholder_encounters(db, f"patient:{demographic_no}")


if __name__ == "__main__":
    # Define a schema for the clinic table for strong data typing.
    logger.debug("-- Schema Definition (run this once)")
    logger.debug("DEFINE TABLE clinic SCHEMAFULL;")
    logger.debug("DEFINE FIELD name ON clinic TYPE string;")
    logger.debug("DEFINE FIELD address ON clinic TYPE object;")
    logger.debug("DEFINE FIELD address.street ON clinic TYPE string;")
    logger.debug("DEFINE FIELD address.city ON clinic TYPE string;")
    logger.debug("DEFINE FIELD address.state ON clinic TYPE string;")
    logger.debug("DEFINE FIELD address.zip ON clinic TYPE string;")
    logger.debug("DEFINE FIELD address.country ON clinic TYPE string;")
    logger.debug("DEFINE FIELD location ON clinic TYPE point;")
    logger.debug("-" * 30)

    # Create instances of the Clinic class for some sample clinics.
    # Coordinates are in (longitude, latitude) order.
    clinic1 = Clinic(
        name="Downtown Health Clinic",
        street="123 Main St",
        city="Metropolis",
        state="CA",
        zip_code="90210",
        country="USA",
        longitude=-118.40,
        latitude=34.07,
    )

    clinic2 = Clinic(
        name="Uptown Wellness Center",
        street="456 Oak Ave",
        city="Metropolis",
        state="CA",
        zip_code="90212",
        country="USA",
        longitude=-118.42,
        latitude=34.09,
    )

    clinic3 = Clinic(
        name="Seaside Medical Group",
        street="789 Ocean Blvd",
        city="Bayview",
        state="CA",
        zip_code="90215",
        country="USA",
        longitude=-118.49,
        latitude=34.01,
    )

    # Generate and print the SurrealQL queries
    logger.debug("-- Generated SurrealQL CREATE Statements")
    query1 = generate_surrealql_create_query(clinic1)
    logger.debug(query1)

    query2 = generate_surrealql_create_query(clinic2)
    logger.debug(query2)

    query3 = generate_surrealql_create_query(clinic3)
    logger.debug(query3)

    # Example of how you might query this data
    logger.debug("-" * 30)
    logger.debug("-- Example Query: Find clinics within 5km of a point")
    # A point somewhere in Metropolis
    search_point_lon = -118.41
    search_point_lat = 34.08
    logger.debug(
        f"SELECT name, address, location, geo::distance(location, ({search_point_lon}, {search_point_lat})) AS distance"
    )
    logger.debug("FROM clinic")
    logger.debug(
        f"WHERE geo::distance(location, ({search_point_lon}, {search_point_lat})) < 5000;"
    )


def test() -> None:
    """
    Test function to demonstrate the functionality of the Clinic class and database operations.
    :return: None
    """
    import asyncio
    import random

    async def run_tests() -> None:
        """
        Runs a series of tests to demonstrate the functionality of the Clinic class and database operations.
        :return: None
        """
        await client.connect()

        random_name = f"Clinic {random.randint(1, 1000)}"

        lon = random.uniform(-115.0, -120.0)
        lat = random.uniform(30.0, 35.0)

        # Create a clinic
        clinic = Clinic(
            name=random_name,
            street="123 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            longitude=lon,
            latitude=lat,
        )
        clinic_id = await create_clinic(clinic)
        logger.debug(f"Created clinic with ID: {clinic_id}")

        # Retrieve the clinic by ID
        retrieved_clinic = None
        if clinic_id is not None:
            retrieved_clinic = await get_clinic_by_id(clinic_id)
        logger.debug(f"Retrieved clinic: {retrieved_clinic}")

        # Update the clinic
        # clinic.name = "Updated Test Clinic"
        # updated = await update_clinic(clinic_id, clinic)
        # logger.debug(f"Clinic updated: {updated}")

        # Search clinics by location
        nearby_clinics = await search_clinics_by_location(
            -118.0, 34.0, radius=km_m(100)
        )
        logger.debug(f"Nearby clinics: {nearby_clinics}")

        # Delete the clinic
        # deleted = await delete_clinic(clinic_id)
        # logger.debug(f"Clinic deleted: {deleted}")

    asyncio.run(run_tests())
