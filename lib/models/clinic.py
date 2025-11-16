"""
This module defines a Clinic class and provides functions to interact with a SurrealDB database.
"""

import json
from typing import Any, Dict, List, Optional, TypedDict

from amt_nano.db.surreal import DbController

from settings import logger


class GeoJSONPoint(TypedDict):
    """
    A TypedDict for GeoJSON Point objects, defining the expected structure.
    This is useful for type checking and IDE support.
    """

    type: str
    coordinates: List[float]


class Address(TypedDict):
    """
    A TypedDict for Address objects, defining the expected structure.
    This is useful for type checking and IDE support.
    """

    street: str
    city: str
    state: str
    zip: str
    country: str


class ClinicType(TypedDict):
    """
    A TypedDict for Clinic objects, defining the expected structure.
    This is useful for type checking and IDE support.
    """

    name: str
    address: Address
    location: GeoJSONPoint
    longitude: float
    latitude: float
    organization_id: str


class Clinic:
    """
    Represents a medical clinic with its address and geospatial location.
    """

    def __init__(
        self,
        name: str,
        street: str,
        city: str,
        state: str,
        zip_code: str,
        country: str,
        longitude: float,
        latitude: float,
        organization_id: str = "",
    ) -> None:
        """
        Initializes a Clinic object.

        Args:
            name (str): The name of the clinic.
            street (str): The street address.
            city (str): The city.
            state (str): The state or province.
            zip_code (str): The postal or ZIP code.
            country (str): The country.
            longitude (float): The longitude of the clinic's location.
            latitude (float): The latitude of the clinic's location.
        """
        self.name = name
        self.street = street
        self.city = city
        self.state = state
        self.zip_code = zip_code
        self.country = country
        self.longitude = longitude
        self.latitude = latitude
        self.organization_id = organization_id

    @staticmethod
    def from_db(data: dict[str, Any]) -> "Clinic":
        """
        Creates a Clinic object from a dictionary representation typically retrieved from the database.

        Args:
            data (Dict[str, Any]): A dictionary containing clinic attributes.

        Returns:
            Clinic: An instance of the Clinic class.
        """
        return Clinic(
            name=data.get("name", ""),
            street=data.get("address", {}).get("street", ""),
            city=data.get("address", {}).get("city", ""),
            state=data.get("address", {}).get("state", ""),
            zip_code=data.get("address", {}).get("zip", ""),
            country=data.get("address", {}).get("country", ""),
            longitude=data.get("location", {}).get("coordinates", [0, 0])[0],
            latitude=data.get("location", {}).get("coordinates", [0, 0])[1],
            organization_id=data.get("organization_id", ""),
        )

    def to_geojson_point(self) -> GeoJSONPoint:
        """
        Converts the clinic's location to a GeoJSON Point dictionary.
        Note: GeoJSON specifies longitude, then latitude.

        :return: A dictionary representing the clinic's location in GeoJSON format.
        """
        return {"type": "Point", "coordinates": [self.longitude, self.latitude]}

    def to_dict(self) -> ClinicType:
        """
        Converts the Clinic object to a dictionary representation.

        :return: A dictionary containing the clinic's attributes.
        """
        return {
            "name": self.name,
            "address": {
                "street": self.street,
                "city": self.city,
                "state": self.state,
                "zip": self.zip_code,
                "country": self.country,
            },
            "location": self.to_geojson_point(),
            "longitude": self.longitude,
            "latitude": self.latitude,
            "organization_id": self.organization_id,
        }

    def __repr__(self) -> str:
        """
        Provides a string representation of the Clinic object.
        """
        return f"Clinic(name='{self.name}', address='{self.street}, {self.city}, {self.state} {self.zip_code}, {self.country}', location=({self.longitude}, {self.latitude}))"

    @classmethod
    def schema(cls) -> str:
        """
        Defines the schema for the clinic table in SurrealDB.
        :return: The entire schema definition for the table in a single string containing all statements.
        """
        return """
            DEFINE TABLE clinic SCHEMAFULL;
            DEFINE FIELD organization_id ON clinic TYPE record<organization>;
            DEFINE FIELD name ON clinic TYPE string;
            DEFINE FIELD street ON clinic TYPE string;
            DEFINE FIELD city ON clinic TYPE string;
            DEFINE FIELD state ON clinic TYPE string;
            DEFINE FIELD zip_code ON clinic TYPE string;
            DEFINE FIELD country ON clinic TYPE string;
            DEFINE FIELD longitude ON clinic TYPE float;
            DEFINE FIELD latitude ON clinic TYPE float;
            DEFINE FIELD created_at ON clinic TYPE datetime VALUE time::now() READONLY;
            DEFINE FIELD updated_at ON clinic TYPE datetime VALUE time::now();
        """


class ClinicController:
    async def create_clinic(clinic: Clinic) -> Optional[str]:
        """
        Asynchronously creates a clinic record in the SurrealDB database.

        Args:
            clinic (Clinic): The clinic object to be created in the database.

        Returns:
            Optional[str]: The ID of the created clinic record, or None if creation failed.
        """
        db = DbController()
        db.connect()

        data_to_set: Dict[str, Any] = {
            "name": clinic.name,
            "address": {
                "street": clinic.street,
                "city": clinic.city,
                "state": clinic.state,
                "zip": clinic.zip_code,
                "country": clinic.country,
            },
            "location": clinic.to_geojson_point(),
        }
        set_clause = json.dumps(data_to_set, indent=4)
        record_id = clinic.name.lower().replace(" ", "_").replace("'", "")
        query = f"CREATE clinic:{record_id} CONTENT {set_clause};"
        result = db.query(query)
        logger.debug("result", type(result), result)
        return result[0]["id"] if result else None

    async def get_clinic_by_id(clinic_id: str) -> Optional[Dict[str, Any]]:
        """
        Asynchronously retrieves a clinic record by its ID.

        Args:
            clinic_id (str): The ID of the clinic to retrieve.

        Returns:
            dict: The clinic record if found, otherwise None.
        """
        query = f"SELECT * FROM {clinic_id};"
        result = await client.query(query)
        return result[0] if result else None

    async def get_all_clinics() -> List[Dict[str, Any]]:
        """
        Asynchronously retrieves all clinic records from the database.

        Returns:
            list: A list of all clinic records.
        """
        query = "SELECT * FROM clinic;"
        result = await client.query(query)
        return result if result else []

    async def search_clinics_by_location(
        longitude: float, latitude: float, radius: float = 5000
    ) -> List[Dict[str, Any]]:
        """
        Asynchronously searches for clinics within a specified radius of a given location.

        Args:
            longitude (float): The longitude of the search point.
            latitude (float): The latitude of the search point.
            radius (float): The search radius in meters (default is 5000).

        Returns:
            list: A list of clinics within the specified radius.
        """
        query = f"""
        SELECT name, address, location, geo::distance(location, ({longitude}, {latitude})) AS distance
        FROM clinic
        WHERE geo::distance(location, ({longitude}, {latitude})) < {radius};
        """
        result = await client.query(query)
        return result if result else []

    async def update_clinic(clinic_id: str, clinic: Clinic) -> bool:
        """
        Asynchronously updates a clinic record in the database.

        Args:
            clinic_id (str): The ID of the clinic to update.
            clinic (Clinic): The updated clinic object.

        Returns:
            bool: True if the update was successful, False otherwise.
        """
        query = f"""
        UPDATE clinic:{clinic_id} SET
            name = '{clinic.name}',
            address = {{
                street: '{clinic.street}',
                city: '{clinic.city}',
                state: '{clinic.state}',
                zip: '{clinic.zip_code}',
                country: '{clinic.country}'
            }},
            location = {json.dumps(clinic.to_geojson_point())}
        ;
        """
        result = await client.query(query)
        return len(result) > 0

    async def delete_clinic(clinic_id: str) -> bool:
        """
        Asynchronously deletes a clinic record from the database.

        Args:
            clinic_id (str): The ID of the clinic to delete.

        Returns:
            bool: True if the deletion was successful, False otherwise.
        """
        query = f"DELETE FROM clinic {clinic_id};"
        result = await client.query(query)
        return len(result) > 0
