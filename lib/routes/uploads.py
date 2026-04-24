"""
Uploads API Routes
"""

import os
import uuid
from typing import Any, Dict, Tuple

import boto3  # type: ignore
from amt_nano.db.surreal import DbController
from botocore.config import Config as BotoConfig  # type: ignore
from flask import Blueprint, Response, jsonify, request
from werkzeug.datastructures import FileStorage

from lib.data_types import UserID
from lib.models.upload import (
    FileType,
    Upload,
    UploadStatus,
    create_upload,
    get_upload_by_id,
    get_uploads_by_user,
    update_upload_status,
)
from lib.services.auth_decorators import get_current_user, require_auth
from lib.services.upload_service import process_upload_task
from settings import (
    BUCKET_NAME,
    MINIO_ACCESS_KEY,
    MINIO_ENCOUNTER_RECORDINGS_BUCKET,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    S3_AWS_ACCESS_KEY_ID,
    S3_AWS_SECRET_ACCESS_KEY,
    logger,
)

uploads_bp = Blueprint("uploads", __name__)


def _s3_client():
    endpoint = MINIO_ENDPOINT
    if endpoint:
        if not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
            raise RuntimeError(
                "MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set when MINIO_ENDPOINT is configured"
            )
        secure = os.getenv("MINIO_SECURE", "true").lower() == "true"
        scheme = "https" if secure else "http"
        return boto3.client(
            "s3",
            endpoint_url=f"{scheme}://{endpoint}",
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            region_name="us-east-1",
            config=BotoConfig(signature_version="s3v4"),
        )

    return boto3.client(
        "s3",
        aws_access_key_id=S3_AWS_ACCESS_KEY_ID,
        aws_secret_access_key=S3_AWS_SECRET_ACCESS_KEY,
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        config=BotoConfig(signature_version="s3v4"),
    )


@uploads_bp.route("/api/uploads", methods=["POST"])
@require_auth
def upload_file_route() -> Tuple[Response, int]:
    """
    Upload a file, create Upload record, upload to S3, trigger Celery if needed.
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400
    file: FileStorage = request.files["file"]
    filename = file.filename or ""
    if filename == "":
        return jsonify({"error": "No selected file"}), 400

    file_type = Upload.get_file_type_from_extension(filename)
    uploader_id: UserID = (
        UserID(user.user_id) if not isinstance(user.user_id, UserID) else user.user_id
    )
    s3_key = Upload.generate_s3_key(uploader_id, filename)
    file_size = 0
    try:
        # Upload to S3
        s3 = _s3_client()
        file.seek(0, 2)  # Seek to end to get size
        file_size = file.tell()
        file.seek(0)
        s3.upload_fileobj(file, BUCKET_NAME, s3_key)
        logger.info(f"Uploaded file to S3: {BUCKET_NAME}/{s3_key}")
    except Exception as e:
        logger.error(f"Failed to upload file to S3: {e}")
        return jsonify({"error": "Failed to upload file to S3"}), 500

    # Create Upload record
    upload = Upload(
        uploader=uploader_id,
        file_name=filename,
        file_path=s3_key,
        file_type=file_type,
        bucket_name=BUCKET_NAME,
        status=UploadStatus.PENDING,
        file_size=file_size,
        s3_key=s3_key,
    )
    upload_id = create_upload(upload)
    if not upload_id:
        return jsonify({"error": "Failed to create upload record"}), 500

    # Trigger Celery task if needed
    if file_type in (FileType.PDF, FileType.IMAGE, FileType.AUDIO):
        task = process_upload_task.apply_async(args=[upload_id, file_type.value, s3_key])  # type: ignore
        update_upload_status(upload_id, UploadStatus.PENDING, task_id=task.id)
    else:
        update_upload_status(upload_id, UploadStatus.COMPLETED)

    return jsonify({"id": upload_id, **upload.to_dict()}), 201


@uploads_bp.route("/api/uploads/presign", methods=["POST"])
@require_auth
def presign_upload_route() -> Tuple[Response, int]:
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    body: Dict[str, Any] = request.get_json(force=True)
    encounter_id = body.get("encounterId")
    filename = body.get("filename", "audio.webm")
    content_type = body.get("contentType", "audio/webm")

    if not encounter_id:
        return jsonify({"error": "encounterId is required"}), 400

    ##encounter = get_encounter_by_id(str(encounter_id))
    ##if not encounter: return jsonify({"error": "Encounter not found"}), 404

    # Temporarily bypassing this check for testing...

    bucket = MINIO_ENCOUNTER_RECORDINGS_BUCKET

    ext = str(filename).rsplit(".", 1)[-1] if "." in str(filename) else "webm"
    upload_id = str(uuid.uuid4())
    object_key = f"encounters/{encounter_id}/audio/{upload_id}.{ext}"

    try:
        s3 = _s3_client()
        url = s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket,
                "Key": object_key,
                "ContentType": content_type,
            },
            ExpiresIn=60 * 10,
        )
    except Exception as e:
        logger.error(f"Failed to generate presigned upload url: {e}")
        return jsonify({"error": "Failed to generate presigned upload url"}), 500

    return (
        jsonify(
            {
                "uploadUrl": url,
                "objectKey": object_key,
                "bucket": bucket,
                "contentType": content_type,
                "expiresInSeconds": 600,
                "publicUrlHint": f"{object_key}",
            }
        ),
        200,
    )


@uploads_bp.route("/api/uploads/complete", methods=["POST"])
@require_auth
def upload_complete_route() -> Tuple[Response, int]:
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    body: Dict[str, Any] = request.get_json(force=True)
    encounter_id = body.get("encounterId")
    object_key = body.get("objectKey")
    size = body.get("size")
    sha256 = body.get("sha256")
    filename = body.get("filename", "audio.webm")

    if not encounter_id or not object_key:
        return jsonify({"error": "encounterId and objectKey required"}), 400

    bucket = MINIO_ENCOUNTER_RECORDINGS_BUCKET

    uploader_id: UserID = (
        UserID(user.user_id) if not isinstance(user.user_id, UserID) else user.user_id
    )
    upload = Upload(
        uploader=uploader_id,
        file_name=str(filename),
        file_path=str(object_key),
        file_type=FileType.AUDIO,
        bucket_name=bucket,
        status=UploadStatus.COMPLETED,
        file_size=int(size) if size is not None else 0,
        s3_key=str(object_key),
    )
    upload_id = create_upload(upload)
    if not upload_id:
        return jsonify({"error": "Failed to create upload record"}), 500

    db = DbController()
    try:
        db.connect()
        db.query(
            "UPDATE encounter SET metadata.recording = $recording WHERE note_id = $encounter_id",
            {
                "encounter_id": str(encounter_id),
                "recording": {
                    "bucket": bucket,
                    "object_key": str(object_key),
                    "size": int(size) if size is not None else None,
                    "sha256": sha256,
                    "upload_id": upload_id,
                },
            },
        )
    except Exception as e:
        logger.error(f"Failed to persist encounter recording metadata: {e}")
        return jsonify({"error": "Failed to persist upload metadata"}), 500
    finally:
        db.close()

    return (
        jsonify(
            {
                "ok": True,
                "id": upload_id,
                "encounterId": encounter_id,
                "objectKey": object_key,
                "bucket": bucket,
                "size": size,
                "sha256": sha256,
            }
        ),
        200,
    )


@uploads_bp.route("/api/uploads", methods=["GET"])
@require_auth
def list_uploads_route():
    """
    List uploads for the current user.
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    uploader_id: UserID = (
        UserID(user.user_id) if not isinstance(user.user_id, UserID) else user.user_id
    )
    uploads = get_uploads_by_user(uploader_id)
    return jsonify(uploads), 200


@uploads_bp.route("/api/uploads/<upload_id>", methods=["GET"])
@require_auth
def get_upload_route(upload_id: str) -> Tuple[Response, int]:
    """
    Get details for a specific upload.
    """
    upload = get_upload_by_id(upload_id)
    if not upload:
        return jsonify({"error": "Upload not found"}), 404
    return jsonify(upload), 200


@uploads_bp.route("/api/uploads/audio/<path:object_key>", methods=["GET"])
@require_auth
def download_audio_route(object_key: str):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    # TODO: IMPORTANT: authorize access:
    # - look up encounter id from object_key (it’s in the key)
    # - confirm user can access that encounter (practitioner relationship, etc.)

    try:
        s3 = _s3_client()
        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": MINIO_ENCOUNTER_RECORDINGS_BUCKET, "Key": object_key},
            ExpiresIn=60 * 5,
        )
    except Exception as e:
        logger.error(f"Failed to generate presigned download url: {e}")
        return jsonify({"error": "Failed to generate presigned download url"}), 500

    # Redirect the client to the presigned URL
    return Response(status=302, headers={"Location": url})
