"""
Routes for the education content.
"""

from typing import Tuple

from flask import Response, jsonify

from lib.data_types import EducationContent


def get_education_content_route(topic: str) -> Tuple[Response, int]:
    """
    Get the education content for a specific topic.
    """
    default_content: EducationContent = {
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
