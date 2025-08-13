"""
Routes for the education content.
"""

import asyncio
from typing import Tuple

from flask import Response, jsonify

from lib.data_types import EducationContentType
from lib.models.education import get_education_content_by_topic


def get_education_content_route(topic: str) -> Tuple[Response, int]:
    """
    Get the education content for a specific topic.
    First tries to find content in the database, then returns default content if none found.
    """
    # Try to get content from database first
    try:
        db_content = asyncio.run(get_education_content_by_topic(topic))
    except Exception as e:
        # Log error and fall back to default content
        print(f"Error fetching education content from database: {e}")
        db_content = None
    
    if db_content:
        # Convert database content to EducationContent format
        content: EducationContentType = {
            "title": db_content.get("title", ""),
            "url": db_content.get("url", ""),
            "type": db_content.get("type", ""),
            "category": db_content.get("category", ""),
            "informationCard": {
                "description": db_content.get("informationCard", {}).get("description", ""),
                "features": db_content.get("informationCard", {}).get("features", [])
            },
            "createdAt": db_content.get("createdAt", ""),
            "updatedAt": db_content.get("updatedAt", "")
        }
        return jsonify(content), 200
    
    # Return default content if no database content found
    default_content: EducationContentType = {
        "title": "3D Anatomical Visualization",
        #"url": "https://www.darrenmackenzie.com/threejs/multiaxis_fullscreen",
        "url": "https://www.darrenmackenzie.com/threejs/anatomy_fullscreen",
        "type": "3d_visualization",
        "category": "Anatomy",
        "informationCard": {
            "description": "Explore the human body in 3D with detailed anatomical models.",
            "features": [
                {"title": "Interactive Models", "description": "Rotate and zoom in on 3D models."},
            ]
        },
        "createdAt": "2023-10-01T12:00:00Z",
        "updatedAt": "2023-10-01T12:00:00Z"
    }
    return jsonify(default_content), 200
