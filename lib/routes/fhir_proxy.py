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
    "CarePlan": "patient",
    "CareTeam": "patient",
    "Claim": "patient",
    "ClaimResponse": "patient",
    "ClinicalImpression": "patient",
    "Communication": "subject",
    "CommunicationRequest": "subject",
    "Condition": "patient",
    "Consent": "patient",
    "Contract": "patient",
    "Coverage": "patient",
    "DetectedIssue": "patient",
    "DeviceUseStatement": "patient",
    "DiagnosticReport": "patient",
    "DocumentReference": "patient",
    "Encounter": "patient",
    "EpisodeOfCare": "patient",
    "ExplanationOfBenefit": "patient",
    "FamilyMemberHistory": "patient",
    "Flag": "patient",
    "Goal": "patient",
    "ImagingStudy": "patient",
    "Immunization": "patient",
    "Invoice": "subject",
    "List": "patient",
    "Medication": None,
    "MedicationAdministration": "patient",
    "MedicationDispense": "patient",
    "MedicationRequest": "patient",
    "MedicationStatement": "patient",
    "NutritionOrder": "patient",
    "Observation": "patient",
    "PaymentNotice": None,
    "PaymentReconciliation": None,
    "Procedure": "patient",
    "QuestionnaireResponse": "patient",
    "RelatedPerson": "patient",
    "RiskAssessment": "patient",
    "ServiceRequest": "patient",
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
        if resource_type in PATIENT_DATA_TYPES and resource_type not in ("Practitioner", "Organization"):
            raise ValueError("Provider access to patient data is not yet configured")
        if resource_type == "Practitioner" and resource_id is not None:
            if user.fhir_practitioner_id is not None and resource_id != user.fhir_practitioner_id:
                raise ValueError("Provider may only access their own Practitioner resource")
        return

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
