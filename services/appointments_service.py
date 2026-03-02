# services/appointments_service.py
"""
Service for managing appointments and their lifecycle.
Handles CRUD operations and linking to journal entries.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, date
import uuid


class AppointmentsService:
    """Handles all appointment-related database operations"""

    def __init__(self, supabase_client):
        """
        Initialize with a Supabase client.

        Args:
            supabase_client: Initialized Supabase client instance
        """
        self.supabase = supabase_client

    async def create_appointment(
        self,
        user_id: str,
        family_id: str,
        title: str,
        scheduled_date: str,
        scheduled_time: Optional[str] = None,
        provider_name: Optional[str] = None,
        location: Optional[str] = None,
        appointment_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new appointment.

        Args:
            user_id: User identifier
            family_id: Family group identifier
            title: Appointment title/description
            scheduled_date: Date in YYYY-MM-DD format
            scheduled_time: Optional time in HH:MM format
            provider_name: Optional healthcare provider name
            location: Optional location/facility name
            appointment_type: Optional type (checkup, follow-up, lab, imaging, specialist)

        Returns:
            Created appointment record
        """
        appointment_data = {
            "user_id": user_id,
            "family_id": family_id,
            "title": title,
            "scheduled_date": scheduled_date,
            "scheduled_time": scheduled_time,
            "provider_name": provider_name,
            "location": location,
            "appointment_type": appointment_type,
            "status": "scheduled"
        }

        result = self.supabase.table("appointments").insert(appointment_data).execute()

        if result.data:
            print(f"Created appointment: {result.data[0]['id']}")
            return result.data[0]

        raise Exception("Failed to create appointment")

    async def get_appointment(self, appointment_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single appointment by ID with its talking points.

        Args:
            appointment_id: UUID of the appointment

        Returns:
            Appointment record with talking_points array, or None if not found
        """
        # Get appointment
        result = self.supabase.table("appointments") \
            .select("*") \
            .eq("id", appointment_id) \
            .execute()

        if not result.data:
            return None

        appointment = result.data[0]

        # Get talking points for this appointment
        points_result = self.supabase.table("talking_points") \
            .select("*") \
            .eq("appointment_id", appointment_id) \
            .order("sort_order") \
            .execute()

        appointment["talking_points"] = points_result.data or []
        appointment["talking_points_count"] = len(appointment["talking_points"])

        return appointment

    async def list_appointments(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        List all appointments for a user.

        Args:
            user_id: User identifier
            status: Optional status filter (scheduled, completed, cancelled)
            limit: Maximum number of results

        Returns:
            List of appointments with talking_points_count
        """
        query = self.supabase.table("appointments") \
            .select("*") \
            .eq("user_id", user_id)

        if status:
            query = query.eq("status", status)

        result = query.order("scheduled_date", desc=True) \
            .limit(limit) \
            .execute()

        appointments = result.data or []

        # Get talking points counts for all appointments
        if appointments:
            appointment_ids = [a["id"] for a in appointments]
            points_result = self.supabase.table("talking_points") \
                .select("appointment_id") \
                .in_("appointment_id", appointment_ids) \
                .execute()

            # Count points per appointment
            counts = {}
            for point in (points_result.data or []):
                appt_id = point["appointment_id"]
                counts[appt_id] = counts.get(appt_id, 0) + 1

            # Add counts to appointments
            for appointment in appointments:
                appointment["talking_points_count"] = counts.get(appointment["id"], 0)

        return appointments

    async def get_appointments_for_month(
        self,
        user_id: str,
        year: int,
        month: int
    ) -> List[Dict[str, Any]]:
        """
        Get appointments for a specific calendar month.

        Args:
            user_id: User identifier
            year: Year (e.g., 2026)
            month: Month (1-12)

        Returns:
            List of appointments in the month with talking_points_count
        """
        # Calculate date range for the month
        start_date = f"{year}-{month:02d}-01"

        # Calculate end date (first day of next month)
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"

        result = self.supabase.table("appointments") \
            .select("*") \
            .eq("user_id", user_id) \
            .gte("scheduled_date", start_date) \
            .lt("scheduled_date", end_date) \
            .order("scheduled_date") \
            .order("scheduled_time") \
            .execute()

        appointments = result.data or []

        # Get talking points counts
        if appointments:
            appointment_ids = [a["id"] for a in appointments]
            points_result = self.supabase.table("talking_points") \
                .select("appointment_id") \
                .in_("appointment_id", appointment_ids) \
                .execute()

            counts = {}
            for point in (points_result.data or []):
                appt_id = point["appointment_id"]
                counts[appt_id] = counts.get(appt_id, 0) + 1

            for appointment in appointments:
                appointment["talking_points_count"] = counts.get(appointment["id"], 0)

        return appointments

    async def update_appointment(
        self,
        appointment_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an appointment.

        Args:
            appointment_id: UUID of the appointment
            updates: Dictionary of fields to update

        Returns:
            Updated appointment record
        """
        # Filter to only allowed fields
        allowed_fields = {
            "title", "scheduled_date", "scheduled_time",
            "provider_name", "location", "appointment_type", "status"
        }
        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

        if not filtered_updates:
            return await self.get_appointment(appointment_id)

        result = self.supabase.table("appointments") \
            .update(filtered_updates) \
            .eq("id", appointment_id) \
            .execute()

        if result.data:
            return result.data[0]
        return None

    async def delete_appointment(self, appointment_id: str) -> bool:
        """
        Delete an appointment (cascades to talking_points).

        Args:
            appointment_id: UUID of the appointment

        Returns:
            True if deleted successfully
        """
        result = self.supabase.table("appointments") \
            .delete() \
            .eq("id", appointment_id) \
            .execute()

        print(f"Deleted appointment: {appointment_id}")
        return True

    async def link_to_journal_entry(
        self,
        appointment_id: str,
        entry_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Link an appointment to a journal entry after a visit.
        Also marks the appointment as completed.

        Args:
            appointment_id: UUID of the appointment
            entry_id: ID of the journal entry

        Returns:
            Updated appointment record
        """
        result = self.supabase.table("appointments") \
            .update({
                "linked_entry_id": entry_id,
                "linked_at": datetime.utcnow().isoformat(),
                "status": "completed"
            }) \
            .eq("id", appointment_id) \
            .execute()

        if result.data:
            print(f"Linked appointment {appointment_id} to entry {entry_id}")
            return result.data[0]
        return None

    async def unlink_journal_entry(self, appointment_id: str) -> Optional[Dict[str, Any]]:
        """
        Remove the link between an appointment and a journal entry.

        Args:
            appointment_id: UUID of the appointment

        Returns:
            Updated appointment record
        """
        result = self.supabase.table("appointments") \
            .update({
                "linked_entry_id": None,
                "linked_at": None
            }) \
            .eq("id", appointment_id) \
            .execute()

        if result.data:
            return result.data[0]
        return None

    async def get_appointments_for_date(
        self,
        user_id: str,
        target_date: str
    ) -> List[Dict[str, Any]]:
        """
        Get all appointments for a specific date.
        Useful for "Today's Appointments" view.

        Args:
            user_id: User identifier
            target_date: Date in YYYY-MM-DD format

        Returns:
            List of appointments on that date
        """
        result = self.supabase.table("appointments") \
            .select("*") \
            .eq("user_id", user_id) \
            .eq("scheduled_date", target_date) \
            .order("scheduled_time") \
            .execute()

        return result.data or []

    async def get_unlinked_past_appointments(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get past appointments without linked journal entries.
        These are appointments that need follow-up.

        Args:
            user_id: User identifier
            limit: Maximum number of results

        Returns:
            List of unlinked past appointments
        """
        today = date.today().isoformat()

        result = self.supabase.table("appointments") \
            .select("*") \
            .eq("user_id", user_id) \
            .lt("scheduled_date", today) \
            .is_("linked_entry_id", "null") \
            .eq("status", "scheduled") \
            .order("scheduled_date", desc=True) \
            .limit(limit) \
            .execute()

        return result.data or []

    async def get_upcoming_appointments(
        self,
        user_id: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get upcoming scheduled appointments.

        Args:
            user_id: User identifier
            limit: Maximum number of results

        Returns:
            List of upcoming appointments
        """
        today = date.today().isoformat()

        result = self.supabase.table("appointments") \
            .select("*") \
            .eq("user_id", user_id) \
            .gte("scheduled_date", today) \
            .eq("status", "scheduled") \
            .order("scheduled_date") \
            .order("scheduled_time") \
            .limit(limit) \
            .execute()

        appointments = result.data or []

        # Get talking points counts
        if appointments:
            appointment_ids = [a["id"] for a in appointments]
            points_result = self.supabase.table("talking_points") \
                .select("appointment_id") \
                .in_("appointment_id", appointment_ids) \
                .execute()

            counts = {}
            for point in (points_result.data or []):
                appt_id = point["appointment_id"]
                counts[appt_id] = counts.get(appt_id, 0) + 1

            for appointment in appointments:
                appointment["talking_points_count"] = counts.get(appointment["id"], 0)

        return appointments
