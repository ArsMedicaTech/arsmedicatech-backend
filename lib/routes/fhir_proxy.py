"""
FHIR BFF proxy for the Flutter web app.

Routes authenticated Flutter requests to the Envoy fhir-gateway, attaching a
server-side Keycloak token and enforcing the authorization rules from the
FHIR_PROXY_SPEC.
"""

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from flask import Blueprint, Response, g, jsonify, request

from lib.services.auth_decorators import require_auth
from lib.services.fhir_client import _fhir_headers
from lib.services.user_service import UserService
from lib.models.user.user import User
from settings import FHIR_GATEWAY_URL, logger


fhir_proxy_bp = Blueprint("fhir_proxy", __name__)

FHIR_ID_RE = re.compile(r"^[A-Za-z0-9\-\.]{1,64}$")
MAX_COUNT = 100
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

# Resource types that a patient may access through their compartment.
PATIENT_SCOPED_TYPES = {
    "Patient",
    "Account",
    "AdverseEvent",
    "AllergyIntolerance",
    "Appointment",
    "BodyStructure",
    "CarePlan",
    "CareTeam",
    "Claim",
    "ClaimResponse",
    "ClinicalImpression",
    "Communication",
    "CommunicationRequest",
    "Condition",
    "Consent",
    "Contract",
    "Coverage",
    "DetectedIssue",
    "DeviceUseStatement",
    "DiagnosticReport",
    "DocumentReference",
    "Encounter",
    "EpisodeOfCare",
    "ExplanationOfBenefit",
    "FamilyMemberHistory",
    "Flag",
    "Goal",
    "ImagingStudy",
    "Immunization",
    "Invoice",
    "List",
    "Medication",
    "MedicationAdministration",
    "MedicationDispense",
    "MedicationRequest",
    "MedicationStatement",
    "NutritionOrder",
    "Observation",
    "PaymentNotice",
    "PaymentReconciliation",
    "Procedure",
    "QuestionnaireResponse",
    "RelatedPerson",
    "RiskAssessment",
    "ServiceRequest",
    "Specimen",
}

# Which search parameter should be used to restrict a patient-scoped resource
# to the authenticated patient's compartment. ``Patient`` is handled separately
# via _id. A key of None means the resource cannot be searched by patient and
# direct reads by id are the only patient-permissible access.
PATIENT_SEARCH_PARAM = {
    "Account": "patient",
    "AdverseEvent": "subject",
    "AllergyIntolerance": "patient",
    "Appointment": "patient",
    "BodyStructure": "patient",
    "CarePlan": "subject",
    "CareTeam": "patient",
    "Claim": "patient",
    "ClaimResponse": "patient",
    "ClinicalImpression": "patient",
    "Communication": "subject",
    "CommunicationRequest": "subject",
    "Condition": "subject",
    "Consent": "patient",
    "Contract": "patient",
    "Coverage": "patient",
    "DetectedIssue": "patient",
    "DeviceUseStatement": "patient",
    "DiagnosticReport": "subject",
    "DocumentReference": "subject",
    "Encounter": "subject",
    "EpisodeOfCare": "patient",
    "ExplanationOfBenefit": "patient",
    "FamilyMemberHistory": "patient",
    "Flag": "patient",
    "Goal": "subject",
    "ImagingStudy": "subject",
    "Immunization": "patient",
    "Invoice": "subject",
    "List": "patient",
    "Medication": None,
    "MedicationAdministration": "patient",
    "MedicationDispense": "patient",
    "MedicationRequest": "patient",
    "MedicationStatement": "subject",
    "NutritionOrder": "patient",
    "Observation": "subject",
    "PaymentNotice": None,
    "PaymentReconciliation": None,
    "Procedure": "patient",
    "QuestionnaireResponse": "subject",
    "RelatedPerson": "patient",
    "RiskAssessment": "patient",
    "ServiceRequest": "subject",
    "Specimen": None,
}

# Resource types that are considered patient data for the fail-closed provider
# policy. Any other resource type is treated as non-patient data and allowed.
PATIENT_DATA_TYPES = PATIENT_SCOPED_TYPES.copy()

# Fallback resource allowlist.  In production the real HAPI metadata is fetched
# on first request to keep the allowlist current.
DEFAULT_FHIR_RESOURCE_TYPES = {
    "Account",
    "ActivityDefinition",
    "AdverseEvent",
    "AllergyIntolerance",
    "Appointment",
    "AppointmentResponse",
    "AuditEvent",
    "Basic",
    "Binary",
    "BiologicallyDerivedProduct",
    "BodyStructure",
    "Bundle",
    "CapabilityStatement",
    "CarePlan",
    "CareTeam",
    "CatalogEntry",
    "ChargeItem",
    "ChargeItemDefinition",
    "Claim",
    "ClaimResponse",
    "ClinicalImpression",
    "CodeSystem",
    "Communication",
    "CommunicationRequest",
    "CompartmentDefinition",
    "Composition",
    "ConceptMap",
    "Condition",
    "Consent",
    "Contract",
    "Coverage",
    "CoverageEligibilityRequest",
    "CoverageEligibilityResponse",
    "DetectedIssue",
    "Device",
    "DeviceDefinition",
    "DeviceMetric",
    "DeviceRequest",
    "DeviceUseStatement",
    "DiagnosticReport",
    "DocumentManifest",
    "DocumentReference",
    "EffectEvidenceSynthesis",
    "Encounter",
    "Endpoint",
    "EnrollmentRequest",
    "EnrollmentResponse",
    "EpisodeOfCare",
    "EventDefinition",
    "Evidence",
    "EvidenceVariable",
    "ExampleScenario",
    "ExplanationOfBenefit",
    "FamilyMemberHistory",
    "Flag",
    "Goal",
    "GraphDefinition",
    "Group",
    "GuidanceResponse",
    "HealthcareService",
    "ImagingStudy",
    "Immunization",
    "ImmunizationEvaluation",
    "ImmunizationRecommendation",
    "ImplementationGuide",
    "InsurancePlan",
    "Invoice",
    "Library",
    "Linkage",
    "List",
    "Location",
    "Measure",
    "MeasureReport",
    "Media",
    "Medication",
    "MedicationAdministration",
    "MedicationDispense",
    "MedicationKnowledge",
    "MedicationRequest",
    "MedicationStatement",
    "MedicinalProduct",
    "MedicinalProductAuthorization",
    "MedicinalProductContraindication",
    "MedicinalProductIndication",
    "MedicinalProductIngredient",
    "MedicinalProductInteraction",
    "MedicinalProductManufactured",
    "MedicinalProductPackaged",
    "MedicinalProductPharmaceutical",
    "MedicinalProductUndesirableEffect",
    "MessageDefinition",
    "MessageHeader",
    "MolecularSequence",
    "NamingSystem",
    "NutritionOrder",
    "Observation",
    "OperationDefinition",
    "OperationOutcome",
    "Organization",
    "OrganizationAffiliation",
    "Parameters",
    "Patient",
    "PaymentNotice",
    "PaymentReconciliation",
    "Person",
    "PlanDefinition",
    "Practitioner",
    "PractitionerRole",
    "Procedure",
    "Provenance",
    "Questionnaire",
    "QuestionnaireResponse",
    "RelatedPerson",
    "RequestGroup",
    "ResearchDefinition",
    "ResearchElementDefinition",
    "ResearchStudy",
    "ResearchSubject",
    "RiskAssessment",
    "RiskEvidenceSynthesis",
    "Schedule",
    "SearchParameter",
    "ServiceRequest",
    "Slot",
    "Specimen",
    "SpecimenDefinition",
    "StructureDefinition",
    "StructureMap",
    "Subscription",
    "Substance",
    "SubstanceNucleicAcid",
    "SubstancePolymer",
    "SubstanceProtein",
    "SubstanceReferenceInformation",
    "SubstanceSpecification",
    "SubstanceSourceMaterial",
    "SupplyDelivery",
    "SupplyRequest",
    "Task",
    "TerminologyCapabilities",
    "TestReport",
    "TestScript",
    "ValueSet",
    "VerificationResult",
    "VisionPrescription",
}

_fhir_resource_types: Optional[set] = None
_fhir_resource_types_fetched_at: float = 0.0


def _fetch_fhir_resource_types() -> Optional[set]:
    try:
        url = f"{FHIR_GATEWAY_URL.rstrip('/')}/metadata"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"FHIR metadata fetch failed: {resp.status_code}")
            return None
        data = resp.json()
        types: set = set()
        for rest in data.get("rest", []):
            for resource in rest.get("resource", []):
                t = resource.get("type")
                if t:
                    types.add(t)
        if not types:
            logger.warning("FHIR metadata contained no resource types")
            return None
        return types
    except Exception as exc:
        logger.warning(f"FHIR metadata fetch error: {exc}")
        return None


def _get_fhir_resource_types() -> set:
    global _fhir_resource_types, _fhir_resource_types_fetched_at
    now = time.time()
    if _fhir_resource_types is None or now - _fhir_resource_types_fetched_at > 300:
        types = _fetch_fhir_resource_types()
        if types:
            _fhir_resource_types = types
            _fhir_resource_types_fetched_at = now
        else:
            _fhir_resource_types = DEFAULT_FHIR_RESOURCE_TYPES.copy()
            _fhir_resource_types_fetched_at = now
    return _fhir_resource_types


def _load_user() -> Optional[User]:
    user_id = getattr(g, "user_id", None)
    if not user_id:
        return None
    user_service = UserService()
    user_service.connect()
    try:
        return user_service.get_user_by_id(str(user_id))
    finally:
        user_service.close()


def _parse_path(subpath: str) -> Tuple[str, Optional[str], Optional[str], bool]:
    if not subpath:
        raise ValueError("Empty FHIR path")
    if "$" in subpath or "/_search" in subpath:
        raise ValueError("FHIR operations are not permitted through the proxy")
    segments = subpath.split("/")
    if not segments:
        raise ValueError("Empty FHIR path")
    if any(seg == "" for seg in segments):
        raise ValueError("Malformed FHIR path")

    resource_type = segments[0]
    if len(segments) == 1:
        return resource_type, None, None, False
    if len(segments) == 2:
        if segments[1] == "_history":
            return resource_type, None, None, True
        if not FHIR_ID_RE.match(segments[1]):
            raise ValueError("Malformed resource id")
        return resource_type, segments[1], None, False
    if len(segments) == 3:
        if segments[1] != "_history" and segments[2] == "_history":
            if not FHIR_ID_RE.match(segments[1]):
                raise ValueError("Malformed resource id")
            return resource_type, segments[1], None, True
        raise ValueError("Unsupported FHIR path")
    if len(segments) == 4:
        if segments[2] == "_history":
            if not FHIR_ID_RE.match(segments[1]) or not FHIR_ID_RE.match(segments[3]):
                raise ValueError("Malformed resource or version id")
            return resource_type, segments[1], segments[3], True
        raise ValueError("Unsupported FHIR path")
    raise ValueError("Unsupported FHIR path")


def _validate_resource_type(resource_type: str) -> None:
    if resource_type not in _get_fhir_resource_types():
        raise ValueError(f"Unknown resource type: {resource_type}")


def _validate_search_params(params: Dict[str, List[str]]) -> None:
    for key in params:
        if key in ("_include", "_revinclude") or key.startswith("_include:") or key.startswith("_revinclude:"):
            raise ValueError("_include/_revinclude is not permitted")
        if key == "_has" or key.startswith("_has:"):
            raise ValueError("_has is not permitted")
        if "." in key:
            raise ValueError("Chained search parameters are not permitted")
        if key == "_query":
            raise ValueError("_query is not permitted")
        if key == "_summary":
            raise ValueError("_summary is not permitted")
        if key.startswith("$"):
            raise ValueError("Operation parameters are not permitted")
    count_values = params.get("_count", [])
    if count_values:
        for idx, v in enumerate(count_values):
            try:
                n = int(v)
            except (ValueError, TypeError):
                raise ValueError("_count must be an integer")
            if n > MAX_COUNT:
                count_values[idx] = str(MAX_COUNT)


def _ref_matches_patient(value: str, fhir_patient_id: str) -> bool:
    expected = f"Patient/{fhir_patient_id}"
    if value == expected or value.endswith(f"/{expected}"):
        return True
    if value == fhir_patient_id:
        return True
    return False


def _contains_patient_reference(obj: Any, fhir_patient_id: str) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "reference" and isinstance(v, str) and _ref_matches_patient(v, fhir_patient_id):
                return True
            if _contains_patient_reference(v, fhir_patient_id):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _contains_patient_reference(item, fhir_patient_id):
                return True
    return False


# CareTeam-scoped provider authorization cache and constants.
_care_team_cache: Dict[Tuple[str, str], Tuple[bool, float]] = {}
CARE_TEAM_CACHE_TTL = 60
LONGITUDINAL_CATEGORY = "LA28865-6"
MAX_PANEL_SIZE = 500


def _strip_patient_prefix(value: str) -> str:
    """Return a bare patient id from 'Patient/{id}' or an absolute reference URL."""
    if not isinstance(value, str):
        return value
    marker = "/Patient/"
    idx = value.rfind(marker)
    if idx != -1:
        return value[idx + len(marker):]
    if value.startswith("Patient/"):
        return value[8:]
    return value


def _flush_care_team_cache() -> None:
    """Flush the in-process CareTeam membership cache."""
    _care_team_cache.clear()


def _is_on_care_team(practitioner_id: str, patient_id: str) -> bool:
    """Active-participant check. Fail closed on any upstream error."""
    cache_key = (practitioner_id, patient_id)
    now = time.time()
    cached = _care_team_cache.get(cache_key)
    if cached is not None:
        result, expires_at = cached
        if now < expires_at:
            return result

    result = False
    try:
        url = f"{FHIR_GATEWAY_URL.rstrip('/')}/CareTeam"
        params = {
            "patient": patient_id,
            "participant": f"Practitioner/{practitioner_id}",
            "status": "active",
            "_summary": "count",
        }
        resp = requests.get(url, params=params, headers=_fhir_headers(), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("total", 0) > 0
        else:
            logger.warning(f"CareTeam membership query failed: status={resp.status_code}")
    except Exception as exc:
        logger.warning(f"CareTeam membership query error: {exc}")

    _care_team_cache[cache_key] = (result, now + CARE_TEAM_CACHE_TTL)
    return result


def _get_active_care_team_count(patient_id: str) -> int:
    """Count of active CareTeam resources for a patient, for bootstrap checks."""
    try:
        url = f"{FHIR_GATEWAY_URL.rstrip('/')}/CareTeam"
        params = {"patient": patient_id, "status": "active", "_summary": "count"}
        resp = requests.get(url, params=params, headers=_fhir_headers(), timeout=10)
        if resp.status_code == 200:
            return resp.json().get("total", 0)
        logger.warning(f"CareTeam count query failed: status={resp.status_code}")
    except Exception as exc:
        logger.warning(f"CareTeam count query error: {exc}")
    # Fail closed: on any error, report a nonzero count so the bootstrap
    # exception does NOT fire and the stricter membership check applies.
    return 1


def _get_provider_panel(practitioner_id: str) -> List[str]:
    """Patient ids where this practitioner is an active CareTeam participant.

    Raises ValueError if the panel exceeds MAX_PANEL_SIZE or the query fails.
    """
    try:
        url = f"{FHIR_GATEWAY_URL.rstrip('/')}/CareTeam"
        params = {
            "participant": f"Practitioner/{practitioner_id}",
            "status": "active",
        }
        resp = requests.get(url, params=params, headers=_fhir_headers(), timeout=10)
        if resp.status_code != 200:
            logger.warning(f"Provider panel query failed: status={resp.status_code}")
            raise ValueError("Failed to load provider panel")

        data = resp.json()
        panel: List[str] = []
        for entry in data.get("entry", []):
            resource = entry.get("resource", {})
            subject = resource.get("subject", {})
            ref = subject.get("reference", "")
            patient_id = _strip_patient_prefix(ref)
            if patient_id:
                panel.append(patient_id)

        if len(panel) > MAX_PANEL_SIZE:
            logger.warning(
                f"Provider panel exceeds MAX_PANEL_SIZE: {len(panel)} > {MAX_PANEL_SIZE}"
            )
            raise ValueError(
                f"Provider panel exceeds {MAX_PANEL_SIZE} patients; "
                "panel-based search is not supported"
            )
        return panel
    except ValueError:
        raise
    except Exception as exc:
        logger.warning(f"Provider panel query error: {exc}")
        raise ValueError("Failed to load provider panel")


def _extract_patient_reference(body: Dict[str, Any]) -> Optional[str]:
    """Bare patient id from a resource body, checking subject/patient/beneficiary."""
    if not isinstance(body, dict):
        return None
    for field in ("subject", "patient", "beneficiary"):
        value = body.get(field)
        if not value:
            continue
        if isinstance(value, dict):
            ref = value.get("reference")
            if isinstance(ref, str):
                return _strip_patient_prefix(ref)
        elif isinstance(value, str):
            return _strip_patient_prefix(value)
    return None


def _extract_resource_patient_id(
    body: Dict[str, Any], resource_type: str, resource_id: Optional[str]
) -> Optional[str]:
    """Best-effort patient id from a fetched resource body."""
    if not isinstance(body, dict):
        return None
    if resource_type == "Patient":
        return body.get("id") or resource_id
    return _extract_patient_reference(body)


def _enforce_scope(
    resource_type: str,
    resource_id: Optional[str],
    method: str,
    params: Dict[str, List[str]],
    body: Optional[Dict[str, Any]],
    user: User,
) -> None:
    role = getattr(g, "user_role", None) or user.role
    if role in ("admin", "superadmin", "administrator"):
        return

    if role == "provider":
        practitioner_id = user.fhir_practitioner_id
        if not practitioner_id:
            logger.warning(
                f"Provider {user.id} ({user.username}) has no fhir_practitioner_id; denying FHIR access"
            )
            raise ValueError("Provider account is not linked to a Practitioner record")

        # CareTeam itself must be handled before the generic patient-data branch.
        if resource_type == "CareTeam":
            if method == "POST":
                if not body:
                    raise ValueError("Write request must include a FHIR resource body")
                patient_id = _extract_patient_reference(body)
                if not patient_id:
                    raise ValueError("CareTeam body must reference a patient")
                if _get_active_care_team_count(patient_id) == 0:
                    # Bootstrap: no active CareTeam exists yet for this patient, so
                    # there is no membership to check against. Any authenticated
                    # provider may create the first one. This does not let a
                    # provider add themselves to an *existing* CareTeam they aren't
                    # on — that path still requires _is_on_care_team below.
                    return
                if not _is_on_care_team(practitioner_id, patient_id):
                    raise ValueError(
                        "Provider is not a participant on this patient's CareTeam"
                    )
                return
            if method == "PUT":
                if not body:
                    raise ValueError("Write request must include a FHIR resource body")
                patient_id = _extract_patient_reference(body)
                if not patient_id:
                    raise ValueError("CareTeam body must reference a patient")
                if not _is_on_care_team(practitioner_id, patient_id):
                    raise ValueError(
                        "Provider is not a participant on this patient's CareTeam"
                    )
                return
            if method == "GET":
                if resource_id is None:
                    patient_values = params.get(PATIENT_SEARCH_PARAM["CareTeam"], [])
                    if not patient_values:
                        raise ValueError(
                            "Provider CareTeam search must be scoped to a patient"
                        )
                    for v in patient_values:
                        if not _is_on_care_team(practitioner_id, _strip_patient_prefix(v)):
                            raise ValueError(
                                "Provider is not a participant on this patient's CareTeam"
                            )
                    return
                # Read-by-id requires fetch-then-authorize in _forward_request.
                g.fhir_post_auth_patient_check = True
                return
            raise ValueError(f"Method {method} not allowed for provider on CareTeam")

        if resource_type not in PATIENT_DATA_TYPES:
            return

        if resource_type == "Patient":
            if resource_id is not None:
                g.fhir_post_auth_patient_check = True
                return
            if method == "POST":
                # Creating a new patient: there's no existing patient to scope
                # against. Let the create through; authorization for *who* may
                # create charts is enforced by the role check above, not panel scope.
                return
            panel = _get_provider_panel(practitioner_id)
            if not panel:
                # Signal fhir_proxy() to return an empty searchset without calling upstream.
                g.fhir_empty_panel = True
                return
            params["_id"] = [",".join(panel)]
            return

        # Remaining patient-scoped types.
        search_param = PATIENT_SEARCH_PARAM.get(resource_type)
        if method == "GET":
            if resource_id is not None:
                g.fhir_post_auth_patient_check = True
                return
            if not search_param:
                raise ValueError(f"Provider search is not supported for {resource_type}")
            patient_values = params.get(search_param, [])
            if not patient_values:
                raise ValueError("Provider searches must be scoped to a specific patient")
            for v in patient_values:
                if not _is_on_care_team(practitioner_id, _strip_patient_prefix(v)):
                    raise ValueError(
                        "Provider is not a participant on this patient's CareTeam"
                    )
            return

        if method in ("POST", "PUT"):
            if not body:
                raise ValueError("Write request must include a FHIR resource body")
            patient_id = _extract_patient_reference(body)
            if not patient_id:
                raise ValueError(
                    f"Resource body must reference a patient for {resource_type}"
                )
            if not _is_on_care_team(practitioner_id, patient_id):
                raise ValueError(
                    "Provider is not a participant on this patient's CareTeam"
                )
            return

        raise ValueError(f"Method {method} not allowed for provider on {resource_type}")

    if role != "patient":
        raise ValueError("Unsupported user role")

    if resource_type == "Patient":
        if resource_id is not None:
            if resource_id != user.fhir_patient_id:
                raise ValueError("Patient may only access their own Patient record")
            return
        _id_values = params.get("_id", [])
        if _id_values:
            if user.fhir_patient_id not in _id_values:
                raise ValueError("_id must reference the patient's own record")
            return
        params.setdefault("_id", []).append(user.fhir_patient_id)
        return

    if resource_type not in PATIENT_SCOPED_TYPES:
        raise ValueError("Resource type is not accessible to patients")

    expected = f"Patient/{user.fhir_patient_id}"

    if method == "GET":
        if resource_id is None:
            search_param = PATIENT_SEARCH_PARAM.get(resource_type)
            if search_param is None:
                raise ValueError(f"Patient-scoped search is not supported for {resource_type}")
            existing = params.get(search_param, [])
            if existing:
                for v in existing:
                    if not _ref_matches_patient(v, user.fhir_patient_id):
                        raise ValueError(f"Conflicting {search_param} parameter")
                return
            params.setdefault(search_param, []).append(expected)
        return

    if method in ("POST", "PUT"):
        if not body:
            raise ValueError("Write request must include a FHIR resource body")
        body_id = body.get("id")
        if body_id is not None and resource_id is not None and body_id != resource_id:
            raise ValueError("Resource id in body does not match request path")
        if resource_type == "Patient":
            if body_id is not None and body_id != user.fhir_patient_id:
                raise ValueError("Patient may only write their own Patient record")
            return
        if not _contains_patient_reference(body, user.fhir_patient_id):
            raise ValueError("Resource body must reference the authenticated patient")
        return

    if method == "PATCH":
        if resource_type == "Patient" and resource_id == user.fhir_patient_id:
            return
        raise ValueError(f"PATCH not allowed for patient on {resource_type}")

    if method == "DELETE":
        if resource_type == "Patient" and resource_id == user.fhir_patient_id:
            return
        raise ValueError(f"DELETE not allowed for patient on {resource_type}")

    raise ValueError(f"Method {method} not allowed")


def _prepare_request_headers() -> Dict[str, str]:
    headers = _fhir_headers()
    client_content_type = request.headers.get("Content-Type")
    if client_content_type:
        headers["Content-Type"] = client_content_type
    client_accept = request.headers.get("Accept")
    if client_accept:
        headers["Accept"] = client_accept
    for h in ("Prefer", "If-Match", "If-None-Exist"):
        if h in request.headers:
            headers[h] = request.headers[h]
    return headers


def _audit_log(
    user: User,
    method: str,
    resource_type: str,
    resource_id: Optional[str],
    query_params: Dict[str, Any],
    status: Optional[int],
    decision: str,
) -> None:
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user_id": str(user.id) if user.id else None,
        "username": user.username,
        "role": user.role,
        "method": method,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "query_params": query_params,
        "upstream_status": status,
        "decision": decision,
    }
    logger.info(json.dumps(payload))


def _handle_error(
    user: Optional[User],
    status: int,
    method: str,
    resource_type: str,
    resource_id: Optional[str],
    query_params: Dict[str, Any],
    message: str,
) -> Tuple[Response, int]:
    if user:
        _audit_log(user, method, resource_type, resource_id, query_params, status, "deny")
    return jsonify({"error": message}), status


def _forward_request(
    method: str,
    url: str,
    params: Dict[str, List[str]],
    data: bytes,
    headers: Dict[str, str],
    user: User,
    resource_type: str,
    resource_id: Optional[str],
    query_params: Dict[str, Any],
) -> Response:
    try:
        resp = requests.request(
            method,
            url,
            params=params,
            data=data,
            headers=headers,
            timeout=30,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        logger.error(f"FHIR upstream request failed: {exc}")
        _audit_log(user, method, resource_type, resource_id, query_params, 502, "allow")
        return jsonify({"error": "Upstream FHIR request failed"}), 502

    if method in ("POST", "PUT", "DELETE") and resource_type == "CareTeam" and 200 <= resp.status_code < 300:
        _flush_care_team_cache()

    if getattr(g, "fhir_post_auth_patient_check", False) and 200 <= resp.status_code < 300:
        try:
            body_json = resp.json()
            patient_id = _extract_resource_patient_id(body_json, resource_type, resource_id)
            practitioner_id = user.fhir_practitioner_id
            if (
                not patient_id
                or not practitioner_id
                or not _is_on_care_team(practitioner_id, patient_id)
            ):
                _audit_log(
                    user, method, resource_type, resource_id, query_params, 403, "deny"
                )
                return (
                    jsonify(
                        {
                            "error": "Provider is not a participant on this patient's CareTeam"
                        }
                    ),
                    403,
                )
        except ValueError:
            _audit_log(
                user, method, resource_type, resource_id, query_params, 403, "deny"
            )
            return (
                jsonify(
                    {"error": "Provider is not a participant on this patient's CareTeam"}
                ),
                403,
            )

    out_headers = {}
    for h in ("Content-Type", "Location", "Content-Location", "ETag", "Last-Modified"):
        if h in resp.headers:
            out_headers[h] = resp.headers[h]
    _audit_log(user, method, resource_type, resource_id, query_params, resp.status_code, "allow")
    return Response(resp.content, status=resp.status_code, headers=out_headers)


@fhir_proxy_bp.route("/api/fhir/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@require_auth
def fhir_proxy(subpath: str) -> Response:
    user = _load_user()
    if not user:
        return _handle_error(
            None, 403, request.method, subpath, None, {}, "User not found"
        )

    try:
        resource_type, resource_id, _, _ = _parse_path(subpath)
    except ValueError as exc:
        if "Malformed resource id" in str(exc):
            return _handle_error(user, 400, request.method, subpath, None, {}, str(exc))
        return _handle_error(user, 403, request.method, subpath, None, {}, str(exc))

    _validate_resource_type(resource_type)

    params: Dict[str, List[str]] = request.args.to_dict(flat=False)
    try:
        _validate_search_params(params)
    except ValueError as exc:
        return _handle_error(
            user, 403, request.method, resource_type, resource_id, params, str(exc)
        )

    body: Optional[Dict[str, Any]] = None
    if request.method in ("POST", "PUT"):
        if request.content_type and "json" in request.content_type:
            body = request.get_json(silent=True) or {}

    try:
        _enforce_scope(resource_type, resource_id, request.method, params, body, user)
    except ValueError as exc:
        return _handle_error(
            user, 403, request.method, resource_type, resource_id, params, str(exc)
        )

    if getattr(g, "fhir_empty_panel", False):
        _audit_log(user, request.method, resource_type, resource_id, params, 200, "allow")
        return jsonify(
            {
                "resourceType": "Bundle",
                "type": "searchset",
                "total": 0,
                "entry": [],
            }
        ), 200

    query_string = urlencode(params, doseq=True)
    upstream_url = f"{FHIR_GATEWAY_URL.rstrip('/')}/{subpath}"
    if query_string:
        upstream_url = f"{upstream_url}?{query_string}"

    headers = _prepare_request_headers()
    data = request.get_data() if request.method in ("POST", "PUT", "PATCH") else b""
    return _forward_request(
        request.method,
        upstream_url,
        {},
        data,
        headers,
        user,
        resource_type,
        resource_id,
        params,
    )


def _validate_bundle_entry(entry: Dict[str, Any], user: User) -> None:
    req = entry.get("request", {})
    method = req.get("method")
    url = req.get("url")
    if not method or not url:
        raise ValueError("Bundle entry missing request method or url")
    if method not in ALLOWED_METHODS:
        raise ValueError(f"Method {method} not allowed in Bundle")

    parsed = urlparse(url)
    subpath = parsed.path.lstrip("/")
    query = parsed.query

    resource_type, resource_id, _, _ = _parse_path(subpath)
    _validate_resource_type(resource_type)

    params: Dict[str, List[str]] = {}
    if query:
        params = parse_qs(query, keep_blank_values=True)
    _validate_search_params(params)

    body = entry.get("resource")
    if method in ("POST", "PUT") and not body:
        raise ValueError("Bundle POST/PUT entry missing resource body")
    if method in ("POST", "PUT") and body.get("resourceType") != resource_type:
        raise ValueError("Bundle resource type does not match request url")

    _enforce_scope(resource_type, resource_id, method, params, body, user)


@fhir_proxy_bp.route("/api/fhir", methods=["POST"])
@require_auth
def fhir_proxy_root() -> Tuple[Response, int]:
    user = _load_user()
    if not user:
        return _handle_error(None, 403, request.method, "Bundle", None, {}, "User not found")

    body_bytes = request.get_data()
    try:
        body = json.loads(body_bytes) if body_bytes else None
    except json.JSONDecodeError:
        return _handle_error(user, 400, request.method, "Bundle", None, {}, "Invalid JSON")

    if not isinstance(body, dict) or body.get("resourceType") != "Bundle":
        return _handle_error(user, 400, request.method, "Bundle", None, {}, "Expected a Bundle resource")
    if body.get("type") != "transaction":
        return _handle_error(user, 403, request.method, "Bundle", None, {}, "Only transaction Bundles are accepted")

    entries = body.get("entry", [])
    if not isinstance(entries, list):
        return _handle_error(user, 400, request.method, "Bundle", None, {}, "Bundle entries must be a list")

    for entry in entries:
        if not isinstance(entry, dict):
            return _handle_error(user, 400, request.method, "Bundle", None, {}, "Invalid Bundle entry")
        try:
            _validate_bundle_entry(entry, user)
        except ValueError as exc:
            return _handle_error(user, 403, request.method, "Bundle", None, {}, str(exc))

    headers = _prepare_request_headers()
    upstream_url = FHIR_GATEWAY_URL.rstrip("/")
    return _forward_request(
        "POST",
        upstream_url,
        {},
        body_bytes,
        headers,
        user,
        "Bundle",
        None,
        {"entry_count": len(entries)},
    )
