"""
Appointment model for scheduling functionality
"""

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Optional

from lib.events import AppointmentStatus
from lib.models.common import Model
from settings import logger
from utils.utils import diff_times_in_seconds


class Appointment(Model):
    """
    Model representing a healthcare appointment.
    """

    def __init__(
        self,
        patient_id: str,
        provider_id: str,
        appointment_date: date,
        start_time: time,
        end_time: time,
        appointment_type: str = "consultation",
        status: str = "scheduled",
        notes: Optional[str] = None,
        location: Optional[str] = None,
        id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> None:
        """
        Initialize an Appointment object

        :param patient_id: ID of the patient
        :param provider_id: ID of the healthcare provider
        :param appointment_date: Date of appointment
        :param start_time: Start time
        :param end_time: End time
        :param appointment_type: Type of appointment
        :param status: Current status of appointment
        :param notes: Additional notes
        :param location: Location of appointment
        :param id: Database record ID
        :param created_at: Creation timestamp
        :param updated_at: Last update timestamp

        :raises ValueError: If any required fields are missing or invalid
        :raises TypeError: If any field types are incorrect

        :return: None
        """
        if (
            not patient_id
            or not provider_id
            or not appointment_date
            or not start_time
            or not end_time
        ):
            raise ValueError(
                "Missing required fields: patient_id, provider_id, appointment_date, start_time, end_time"
            )

        self.patient_id = patient_id
        self.provider_id = provider_id
        self.appointment_date = appointment_date
        self.start_time = start_time
        self.end_time = end_time
        self.appointment_type = appointment_type
        self.status = status
        self.notes = notes or ""
        self.location = location or ""
        self.id = id
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert appointment to dictionary for database storage

        :return: Dictionary representation of the appointment
        """
        return {
            "patient_id": self.patient_id,
            "provider_id": self.provider_id,
            "appointment_date": self.appointment_date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "appointment_type": self.appointment_type,
            "status": self.status,
            "notes": self.notes,
            "location": self.location,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Appointment":
        """
        Create appointment from dictionary

        :param data: Dictionary containing appointment data
        :return: Appointment object
        """
        logger.debug(f"Appointment.from_dict called with data: {data}")

        # Convert RecordID to string if it exists
        appointment_id = data.get("id")
        if hasattr(appointment_id, "__str__"):
            appointment_id = str(appointment_id)

        logger.debug(f"Converted appointment_id: {appointment_id}")

        try:
            # Ensure required fields are present and are strings
            required_fields = [
                "patient_id",
                "provider_id",
                "appointment_date",
                "start_time",
                "end_time",
            ]
            for field in required_fields:
                if not isinstance(data.get(field), str) or not data.get(field):
                    raise ValueError(f"Missing or invalid required field: {field}")
            appointment = cls(
                patient_id=str(data.get("patient_id")),
                provider_id=str(data.get("provider_id")),
                appointment_date=data.get("appointment_date"),  # type: ignore We already check if this is in the required fields
                start_time=data.get("start_time"),  # type: ignore See above
                end_time=data.get("end_time"),  # type: ignore See above
                appointment_type=data.get("appointment_type", "consultation"),
                status=data.get("status", "scheduled"),
                notes=data.get("notes"),
                location=data.get("location"),
                id=appointment_id,
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
            )
            logger.debug(f"Successfully created appointment object: {appointment.id}")
            return appointment
        except Exception as e:
            logger.error(f"Failed to create appointment from dict: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def get_duration_minutes(self) -> int:
        """
        Calculate appointment duration in minutes

        :return: Duration in minutes, or 0 if times are invalid
        """
        try:
            duration = diff_times_in_seconds(self.start_time, self.end_time)
            return int(duration / 60)
        except ValueError:
            return 0

    def is_confirmed(self) -> bool:
        """
        Check if appointment is confirmed

        :return: True if appointment is confirmed, False otherwise
        """
        return self.status == AppointmentStatus.CONFIRMED.value

    def is_cancelled(self) -> bool:
        """
        Check if appointment is cancelled

        :return: True if appointment is cancelled, False otherwise
        """
        return self.status == AppointmentStatus.CANCELLED.value

    def is_completed(self) -> bool:
        """
        Check if appointment is completed

        :return: True if appointment is completed, False otherwise
        """
        return self.status == AppointmentStatus.COMPLETED.value

    def can_be_cancelled(self) -> bool:
        """
        Check if appointment can be cancelled

        :return: True if appointment can be cancelled, False otherwise
        """
        return self.status in [
            AppointmentStatus.SCHEDULED.value,
            AppointmentStatus.CONFIRMED.value,
        ]

    def get_datetime(self) -> Optional[datetime]:
        """
        Get full datetime of appointment start

        :return: Datetime object representing appointment start, or None if invalid
        """
        try:
            return datetime.combine(self.appointment_date, self.start_time)
        except ValueError:
            return None

    def is_in_past(self) -> bool:
        """
        Check if appointment is in the past

        :return: True if appointment is in the past, False otherwise
        """
        appointment_dt = self.get_datetime()
        if not appointment_dt:
            return False
        return appointment_dt < datetime.now()

    def is_today(self) -> bool:
        """
        Check if appointment is today

        :return: True if appointment is today, False otherwise
        """
        appointment_dt = self.get_datetime()
        if not appointment_dt:
            return False
        return appointment_dt.date() == datetime.now().date()

    def is_this_week(self) -> bool:
        """
        Check if appointment is this week

        :return: True if appointment is this week, False otherwise
        """
        appointment_dt = self.get_datetime()
        if not appointment_dt:
            return False
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        return week_start.date() <= appointment_dt.date() <= week_end.date()

    @classmethod
    def schema(cls) -> str:
        """
        Defines the schema for the appointment table in SurrealDB.
        :return: The entire schema definition for the table in a single string containing all statements.
        """
        return """
            DEFINE TABLE appointment SCHEMAFULL;
            DEFINE FIELD patient_id ON appointment TYPE record<patient>;
            DEFINE FIELD provider_on ON appointment TYPE string;
            DEFINE FIELD appointment_date ON appointment TYPE datetime;
            DEFINE FIELD start_time ON appointment TYPE datetime;
            DEFINE FIELD end_time ON appointment TYPE datetime;
            DEFINE FIELD appointment_type ON appointment TYPE string;
            DEFINE FIELD status ON appointment TYPE string;
            DEFINE FIELD notes ON appointment TYPE string;
            DEFINE FIELD location ON appointment TYPE string;
            DEFINE FIELD created_at ON appointment TYPE datetime VALUE time::now() READONLY;
            DEFINE FIELD updated_at ON appointment TYPE datetime VALUE time::now();
            DEFINE INDEX idx_appointment_date ON appointment FIELDS appointment_date;
            DEFINE INDEX idx_appointment_provider ON appointment FIELDS provider_id;
            DEFINE INDEX idx_appointment_patient ON appointment FIELDS patient_id;
            DEFINE INDEX idx_appointment_status ON appointment FIELDS status;
            DEFINE INDEX idx_appointment_datetime ON appointment FIELDS appointment_date, start_time;
        """
