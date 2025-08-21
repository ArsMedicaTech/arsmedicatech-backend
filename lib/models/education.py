"""
Models for the education content.
"""

import json
from typing import Any, Dict, List, Optional

from amt_nano.db.surreal import AsyncDbController
from lib.data_types import EducationContentType
from settings import logger


async def get_client() -> AsyncDbController:
    """
    Get the client for the database.
    """
    client = AsyncDbController()
    await client.connect()
    return client


class EducationContent:
    """
    Represents educational content with metadata and information cards.
    """

    def __init__(
        self,
        title: str,
        url: str,
        content_type: str,
        category: str,
        description: str,
        features: List[Dict[str, str]],
        created_at: str = "",
        updated_at: str = "",
    ) -> None:
        """
        Initializes an EducationContent object.

        Args:
            title (str): The title of the educational content.
            url (str): The URL to access the content.
            content_type (str): The type of content (e.g., "3d_visualization", "video", "article").
            category (str): The category of the content (e.g., "Anatomy", "Physiology").
            description (str): The description of the content.
            features (List[Dict[str, str]]): List of features with title and description.
            created_at (str): ISO timestamp when the content was created.
            updated_at (str): ISO timestamp when the content was last updated.
        """
        self.title = title
        self.url = url
        self.content_type = content_type
        self.category = category
        self.description = description
        self.features = features
        self.created_at = created_at
        self.updated_at = updated_at

    @staticmethod
    def from_db(data: Dict[str, Any]) -> "EducationContent":
        """
        Creates an EducationContent object from a dictionary representation typically retrieved from the database.

        Args:
            data (Dict[str, Any]): A dictionary containing education content attributes.

        Returns:
            EducationContent: An instance of the EducationContent class.
        """
        return EducationContent(
            title=data.get("title", ""),
            url=data.get("url", ""),
            content_type=data.get("type", ""),
            category=data.get("category", ""),
            description=data.get("informationCard", {}).get("description", ""),
            features=data.get("informationCard", {}).get("features", []),
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
        )

    def to_dict(self) -> EducationContentType:
        """
        Converts the EducationContent object to a dictionary representation.

        Returns:
            EducationContentType: A dictionary containing the education content's attributes.
        """
        return {
            "title": self.title,
            "url": self.url,
            "type": self.content_type,
            "category": self.category,
            "informationCard": {
                "description": self.description,
                "features": [
                    {"title": f["title"], "description": f["description"]}
                    for f in self.features
                ],
            },
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    def __repr__(self) -> str:
        """
        Provides a string representation of the EducationContent object.
        """
        return f"EducationContent(title='{self.title}', type='{self.content_type}', category='{self.category}')"


def generate_surrealql_create_query(
    content: EducationContent, table_name: str = "education"
) -> str:
    """
    Generates a SurrealQL CREATE statement for a given EducationContent object.

    Args:
        content (EducationContent): The education content object to create a query for.
        table_name (str): The name of the table to insert the content into.

    Returns:
        str: A SurrealQL CREATE statement string.
    """
    data_to_set: Dict[str, Any] = {
        "title": content.title,
        "url": content.url,
        "type": content.content_type,
        "category": content.category,
        "informationCard": {
            "description": content.description,
            "features": content.features,
        },
        "createdAt": content.created_at,
        "updatedAt": content.updated_at,
    }

    set_clause = json.dumps(data_to_set, indent=4)

    # Create a record ID based on the title and category
    record_id = f"{content.category.lower().replace(' ', '_')}_{content.title.lower().replace(' ', '_').replace('(', '').replace(')', '').replace(':', '').replace('/', '_')}"

    query = f"CREATE {table_name}:{record_id} CONTENT {set_clause};"

    return query


async def create_education_content(content: EducationContent) -> Optional[str]:
    """
    Asynchronously creates an education content record in the SurrealDB database.

    Args:
        content (EducationContent): The education content object to be created in the database.

    Returns:
        Optional[str]: The ID of the created education content record, or None if creation failed.
    """
    client = await get_client()
    query = generate_surrealql_create_query(content)
    result = await client.query(query)
    logger.debug("result", type(result), result)
    return result[0]["id"] if result else None


async def get_education_content_by_id(content_id: str) -> Optional[Dict[str, Any]]:
    """
    Asynchronously retrieves an education content record by its ID.

    Args:
        content_id (str): The ID of the education content to retrieve.

    Returns:
        Optional[Dict[str, Any]]: The education content record if found, otherwise None.
    """
    client = await get_client()
    query = f"SELECT * FROM education {content_id};"
    result = await client.query(query)
    return result[0] if result else None


async def get_education_content_by_topic(topic: str) -> Optional[Dict[str, Any]]:
    """
    Asynchronously retrieves education content by topic (title or category).

    Args:
        topic (str): The topic to search for in title or category.

    Returns:
        Optional[Dict[str, Any]]: The education content record if found, otherwise None.
    """
    client = await get_client()
    query = f"""
    SELECT * FROM education 
    WHERE title = '{topic}' OR category = '{topic}' 
    LIMIT 1;
    """
    result = await client.query(query)
    return result[0] if result else None


async def get_all_education_content() -> List[Dict[str, Any]]:
    """
    Asynchronously retrieves all education content records from the database.

    Returns:
        List[Dict[str, Any]]: A list of all education content records.
    """
    client = await get_client()
    query = "SELECT * FROM education;"
    result = await client.query(query)
    return result if result else []


async def get_education_content_by_category(category: str) -> List[Dict[str, Any]]:
    """
    Asynchronously retrieves all education content records by category.

    Args:
        category (str): The category to filter by.

    Returns:
        List[Dict[str, Any]]: A list of education content records in the specified category.
    """
    client = await get_client()
    query = f"SELECT * FROM education WHERE category = '{category}';"
    result = await client.query(query)
    return result if result else []


async def get_education_content_by_type(content_type: str) -> List[Dict[str, Any]]:
    """
    Asynchronously retrieves all education content records by type.

    Args:
        content_type (str): The content type to filter by.

    Returns:
        List[Dict[str, Any]]: A list of education content records of the specified type.
    """
    client = await get_client()
    query = f"SELECT * FROM education WHERE type = '{content_type}';"
    result = await client.query(query)
    return result if result else []


async def update_education_content(content_id: str, content: EducationContent) -> bool:
    """
    Asynchronously updates an education content record in the database.

    Args:
        content_id (str): The ID of the education content to update.
        content (EducationContent): The updated education content object.

    Returns:
        bool: True if the update was successful, False otherwise.
    """
    client = await get_client()
    query = f"""
    UPDATE education:{content_id} SET
        title = '{content.title}',
        url = '{content.url}',
        type = '{content.content_type}',
        category = '{content.category}',
        informationCard = {{
            description: '{content.description}',
            features: {json.dumps(content.features)}
        }},
        updatedAt = '{content.updated_at}'
    ;
    """
    result = await client.query(query)
    return len(result) > 0


async def delete_education_content(content_id: str) -> bool:
    """
    Asynchronously deletes an education content record from the database.

    Args:
        content_id (str): The ID of the education content to delete.

    Returns:
        bool: True if the deletion was successful, False otherwise.
    """
    client = await get_client()
    query = f"DELETE FROM education {content_id};"
    result = await client.query(query)
    return len(result) > 0


def get_education_schema() -> List[str]:
    """
    Returns the SurrealDB schema definition statements for the education table.

    Returns:
        List[str]: List of schema definition statements.
    """
    statements: List[str] = []
    statements.append("DEFINE TABLE education SCHEMAFULL;")
    statements.append("DEFINE FIELD title ON education TYPE string;")
    statements.append("DEFINE FIELD url ON education TYPE string;")
    statements.append("DEFINE FIELD type ON education TYPE string;")
    statements.append("DEFINE FIELD category ON education TYPE string;")
    statements.append("DEFINE FIELD informationCard ON education TYPE object;")
    statements.append(
        "DEFINE FIELD informationCard.description ON education TYPE string;"
    )
    statements.append("DEFINE FIELD informationCard.features ON education TYPE array;")
    statements.append(
        "DEFINE FIELD informationCard.features[*].title ON education TYPE string;"
    )
    statements.append(
        "DEFINE FIELD informationCard.features[*].description ON education TYPE string;"
    )
    statements.append("DEFINE FIELD createdAt ON education TYPE string;")
    statements.append("DEFINE FIELD updatedAt ON education TYPE string;")
    return statements
