"""
This module defines the routes for the organizations API.

They are imported by the main app.py file and wrapped with Flask routing decorators.
"""

from typing import Tuple

from amt_nano.db.surreal import DbController
from flask import Response, jsonify, request

from lib.models.organization import Organization, create_organization
from lib.models.user.user import User
from settings import logger


def get_organization_route(org_id: str) -> Tuple[Response, int]:
    """
    Get a specific organization by its ID.
    Returns the organization or 404 if not found.
    """
    if request.method != "GET":
        return jsonify({"error": "Method not allowed"}), 405

    db = DbController()
    db.connect()
    try:
        org_data = db.select(f"organization:{org_id}")
        if not org_data:
            return jsonify({"error": "Organization not found"}), 404

        org = Organization.from_dict(org_data)
        return jsonify({"organization": org.to_dict()}), 200
    except Exception as e:
        logger.error(f"Error fetching organization {org_id}: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


def get_organizations_route() -> Tuple[Response, int]:
    """
    Return a list of all organizations as JSON.
    """
    db = DbController()
    db.connect()
    try:
        results = db.select_many("organization")
        # Handle result structure
        if results and len(results) > 0:
            if "result" in results[0]:
                orgs = results[0]["result"]
            else:
                orgs = results
            orgs_list = [Organization.from_dict(org).to_dict() for org in orgs]
        else:
            orgs_list = []
        return jsonify({"organizations": orgs_list}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


def create_organization_route() -> Tuple[Response, int]:
    """
    API endpoint to create a new organization.
    Accepts JSON body with: name, org_type, created_by, (optional) description, country, clinic_ids.
    Returns the created organization or error.
    """
    if request.method != "POST":
        return jsonify({"error": "Method not allowed"}), 405

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    name = data.get("name")
    org_type = data.get("org_type")
    created_by = data.get("created_by")
    description = data.get("description", "")
    country = data.get("country", "")
    clinic_ids = data.get("clinic_ids", [])

    if not all([name, org_type, created_by]):
        return (
            jsonify({"error": "Missing required fields: name, org_type, created_by"}),
            400,
        )

    db = DbController()
    db.connect()
    try:
        # Check if user can create more organizations
        user_data = db.select(f"user:{created_by}")
        if not user_data:
            return jsonify({"error": "User not found"}), 404

        user = User.from_dict(user_data)
        if not user.can_create_organization():
            remaining = user.get_remaining_organization_slots()
            return (
                jsonify(
                    {
                        "error": f"Organization limit reached. You can create {user.max_organizations} organization(s) and have already created {user.user_organizations}. Remaining slots: {remaining}"
                    }
                ),
                403,
            )

        org = Organization(
            name=name,
            org_type=org_type,
            created_by=created_by,
            description=description,
            country=country,
            clinic_ids=clinic_ids,
        )

        logger.info(f"Creating organization: {org.to_dict()}")

        org_id = create_organization(org)
        if org_id:
            org.id = org_id

            # Increment user's organization count
            user.increment_organization_count()
            user_update_data = user.to_dict()
            db.update(f"user:{created_by}", user_update_data)

            return jsonify({"organization": org.to_dict(), "id": org_id}), 201
        else:
            return jsonify({"error": "Failed to create organization"}), 500
    except ValueError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


def update_organization_route(org_id: str) -> Tuple[Response, int]:
    """
    Update an existing organization by its ID.
    Accepts JSON body with updated fields.
    Returns the updated organization or error.
    """
    if request.method != "PUT":
        return jsonify({"error": "Method not allowed"}), 405
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    db = DbController()
    db.connect()
    try:
        logger.info(f"Updating organization: {org_id}")
        # Fetch existing org
        org_data = db.select(f"organization:{org_id}")
        if not org_data:
            return jsonify({"error": "Organization not found"}), 404
        org = Organization.from_dict(org_data)
        # Update fields
        for key in ["name", "org_type", "description", "country", "clinic_ids"]:
            if key in data:
                setattr(org, key, data[key])
        # Save updated org
        update_data = org.to_dict()
        db.update(f"organization:{org_id}", update_data)
        return jsonify({"organization": org.to_dict()}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


def get_organization_by_user_id_route(user_id: str) -> Tuple[Response, int]:
    """
    Get an organization by user ID.
    """
    if request.method != "GET":
        return jsonify({"error": "Method not allowed"}), 405

    db = DbController()
    db.connect()
    try:
        # Query for organizations where created_by matches the user_id
        query = f"SELECT * FROM organization WHERE created_by = '{user_id}' LIMIT 1;"
        result = db.query(query)

        if result and len(result) > 0:
            first_result = result[0]
            # Check if result has a 'result' key (common in SurrealDB responses)
            if "result" in first_result and first_result["result"]:
                org_data = first_result["result"][0]
                org = Organization.from_dict(org_data)
                return jsonify({"organization": org.to_dict()}), 200
            # If no 'result' key, check if the first result is the org data
            elif "id" in first_result:
                org = Organization.from_dict(first_result)
                return jsonify({"organization": org.to_dict()}), 200

        return jsonify({"error": "No organization found for this user"}), 404
    except Exception as e:
        logger.error(f"Error fetching organization for user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


def add_clinic_to_organization_route(org_id: str) -> Tuple[Response, int]:
    """
    Add a clinic to an organization.
    Accepts JSON body with clinic_id.
    Returns the updated organization or error.
    """
    if request.method != "POST":
        return jsonify({"error": "Method not allowed"}), 405

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    clinic_id = data.get("clinic_id")
    if not clinic_id:
        return jsonify({"error": "Missing clinic_id"}), 400

    db = DbController()
    db.connect()
    try:
        # Fetch existing org
        org_data = db.select(f"organization:{org_id}")
        if not org_data:
            return jsonify({"error": "Organization not found"}), 404

        org = Organization.from_dict(org_data)

        # Check if clinic exists
        clinic_data = db.select(f"clinic:{clinic_id}")
        if not clinic_data:
            return jsonify({"error": "Clinic not found"}), 404

        # Add clinic to organization if not already present
        if clinic_id not in org.clinic_ids:
            org.clinic_ids.append(clinic_id)

            # Update organization's country if not set and clinic has country
            if (
                not org.country
                and "address" in clinic_data
                and "country" in clinic_data["address"]
            ):
                org.country = clinic_data["address"]["country"]

            # Save updated org
            update_data = org.to_dict()
            db.update(f"organization:{org_id}", update_data)

        return jsonify({"organization": org.to_dict()}), 200
    except Exception as e:
        logger.error(f"Error adding clinic to organization: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


def remove_clinic_from_organization_route(org_id: str) -> Tuple[Response, int]:
    """
    Remove a clinic from an organization.
    Accepts JSON body with clinic_id.
    Returns the updated organization or error.
    """
    if request.method != "DELETE":
        return jsonify({"error": "Method not allowed"}), 405

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    clinic_id = data.get("clinic_id")
    if not clinic_id:
        return jsonify({"error": "Missing clinic_id"}), 400

    db = DbController()
    db.connect()
    try:
        # Fetch existing org
        org_data = db.select(f"organization:{org_id}")
        if not org_data:
            return jsonify({"error": "Organization not found"}), 404

        org = Organization.from_dict(org_data)

        # Remove clinic from organization if present
        if clinic_id in org.clinic_ids:
            org.clinic_ids.remove(clinic_id)

            # Save updated org
            update_data = org.to_dict()
            db.update(f"organization:{org_id}", update_data)

        return jsonify({"organization": org.to_dict()}), 200
    except Exception as e:
        logger.error(f"Error removing clinic from organization: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


def get_organization_clinics_route(org_id: str) -> Tuple[Response, int]:
    """
    Get all clinics for an organization.
    Returns the list of clinics or error.
    """
    if request.method != "GET":
        return jsonify({"error": "Method not allowed"}), 405

    db = DbController()
    db.connect()
    try:
        # Fetch existing org
        org_data = db.select(f"organization:{org_id}")
        if not org_data:
            return jsonify({"error": "Organization not found"}), 404

        org = Organization.from_dict(org_data)

        # Fetch all clinics for this organization
        clinics = []
        for clinic_id in org.clinic_ids:
            clinic_data = db.select(f"clinic:{clinic_id}")
            if clinic_data:
                clinics.append(clinic_data)

        return jsonify({"clinics": clinics}), 200
    except Exception as e:
        logger.error(f"Error fetching organization clinics: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
