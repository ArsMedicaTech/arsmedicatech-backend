"""
Test the education content.
"""
import asyncio
import os
import sys

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from lib.models.education import (
    EducationContent,
    create_education_content,
    delete_education_content,
    get_all_education_content,
    get_education_content_by_id,
    get_education_content_by_topic,
)


def test_education_crud():
    """Test the education CRUD operations."""
    print("Testing Education Content CRUD operations...")
    
    async def run_tests():
        """Run the async tests."""
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
            created_at="2023-10-01T12:00:00Z",
            updated_at="2023-10-01T12:00:00Z"
        )
        
        print(f"Created content object: {content}")
        
        try:
            # Test database operations
            print("\n1. Testing CREATE operation...")
            content_id = await create_education_content(content)
            print(f"Created education content with ID: {content_id}")
            
            if content_id:
                print("\n2. Testing READ operation by ID...")
                retrieved_content = await get_education_content_by_id(content_id)
                print(f"Retrieved content by ID: {retrieved_content}")
                
                print("\n3. Testing READ operation by topic...")
                topic_content = await get_education_content_by_topic("Anatomy")
                print(f"Retrieved content by topic 'Anatomy': {topic_content}")
                
                print("\n4. Testing READ all content...")
                all_content = await get_all_education_content()
                print(f"All education content count: {len(all_content)}")
                
                print("\n5. Testing DELETE operation...")
                deleted = await delete_education_content(content_id)
                print(f"Content deleted: {deleted}")
                
                # Verify deletion
                retrieved_after_delete = await get_education_content_by_id(content_id)
                print(f"Content after deletion: {retrieved_after_delete}")
                
            else:
                print("Failed to create content, skipping other tests")
                
        except Exception as e:
            print(f"Error during testing: {e}")
            print("This might be expected if the database is not running or configured")
            raise e
    
    # Run the async tests
    asyncio.run(run_tests())


def test_education_content_creation():
    """Test creating education content objects."""
    print("\nTesting Education Content object creation...")
    
    content = EducationContent(
        title="Test Content",
        url="https://example.com/test",
        content_type="test",
        category="Test",
        description="Test description",
        features=[{"title": "Test Feature", "description": "Test feature description"}],
        created_at="2023-10-01T12:00:00Z",
        updated_at="2023-10-01T12:00:00Z"
    )
    
    print(f"Created content: {content}")
    print(f"Content title: {content.title}")
    print(f"Content category: {content.category}")
    print(f"Content features count: {len(content.features)}")
    
    # Test to_dict method
    content_dict = content.to_dict()
    print(f"Content as dict: {content_dict}")
    
    print("Education Content object creation test completed!")


if __name__ == "__main__":
    test_education_crud()
    test_education_content_creation()
