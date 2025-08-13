"""
Test the education content.
"""
from amt_nano.db.surreal import AsyncDbController

# Database client
client = AsyncDbController()


from lib.models.education import (
    EducationContent,
    create_education_content,
    delete_education_content,
    get_all_education_content,
    get_education_content_by_id,
    get_education_content_by_topic,
)
from settings import logger


def test() -> None:
    """
    Test function to demonstrate the functionality of the EducationContent class and database operations.
    """
    import asyncio
    from datetime import datetime, timezone

    async def run_tests() -> None:
        """
        Runs a series of tests to demonstrate the functionality of the EducationContent class and database operations.
        """
        await client.connect()

        # Create sample education content
        content = EducationContent(
            title="3D Anatomical Visualization",
            url="https://www.darrenmackenzie.com/threejs/anatomy_fullscreen",
            content_type="3d_visualization",
            category="Anatomy",
            description="Explore the human body in 3D with detailed anatomical models.",
            features=[
                {"title": "Interactive Models", "description": "Rotate and zoom in on 3D models."},
                {"title": "Detailed Views", "description": "Examine specific body systems and organs."}
            ],
            created_at=datetime.now(timezone.utc).isoformat() + "Z",
            updated_at=datetime.now(timezone.utc).isoformat() + "Z"
        )

        # Create the content
        content_id = await create_education_content(content)
        logger.debug(f"Created education content with ID: {content_id}")

        # Retrieve the content by ID
        retrieved_content = None
        if content_id is not None:
            retrieved_content = await get_education_content_by_id(content_id)
        logger.debug(f"Retrieved content: {retrieved_content}")

        # Search by topic
        topic_content = await get_education_content_by_topic("Anatomy")
        logger.debug(f"Content by topic 'Anatomy': {topic_content}")

        # Get all content
        all_content = await get_all_education_content()
        logger.debug(f"All education content: {all_content}")

        # Clean up - delete the test content
        if content_id is not None:
            deleted = await delete_education_content(content_id)
            logger.debug(f"Content deleted: {deleted}")

    asyncio.run(run_tests())


if __name__ == "__main__":
    test()
