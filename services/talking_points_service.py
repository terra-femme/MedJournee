# services/talking_points_service.py
"""
Service for managing talking points (checklist items) for appointments.
Handles CRUD operations, toggle done status, and reordering.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime


class TalkingPointsService:
    """Handles all talking point operations for appointments"""

    def __init__(self, supabase_client):
        """
        Initialize with a Supabase client.

        Args:
            supabase_client: Initialized Supabase client instance
        """
        self.supabase = supabase_client

    async def create_talking_point(
        self,
        appointment_id: str,
        text: str,
        category: str = "general",
        priority: str = "medium"
    ) -> Dict[str, Any]:
        """
        Create a new talking point for an appointment.

        Args:
            appointment_id: UUID of the parent appointment
            text: The talking point text
            category: Category (medication, symptoms, results, questions, general)
            priority: Priority level (high, medium, low)

        Returns:
            Created talking point record
        """
        # Get current max sort_order for this appointment
        result = self.supabase.table("talking_points") \
            .select("sort_order") \
            .eq("appointment_id", appointment_id) \
            .order("sort_order", desc=True) \
            .limit(1) \
            .execute()

        next_order = 0
        if result.data:
            next_order = (result.data[0]["sort_order"] or 0) + 1

        point_data = {
            "appointment_id": appointment_id,
            "text": text,
            "category": category,
            "priority": priority,
            "sort_order": next_order,
            "done": False
        }

        result = self.supabase.table("talking_points").insert(point_data).execute()

        if result.data:
            print(f"Created talking point: {result.data[0]['id']}")
            return result.data[0]

        raise Exception("Failed to create talking point")

    async def get_talking_point(self, point_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single talking point by ID.

        Args:
            point_id: UUID of the talking point

        Returns:
            Talking point record or None if not found
        """
        result = self.supabase.table("talking_points") \
            .select("*") \
            .eq("id", point_id) \
            .execute()

        return result.data[0] if result.data else None

    async def list_talking_points(
        self,
        appointment_id: str,
        include_done: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List all talking points for an appointment.

        Args:
            appointment_id: UUID of the appointment
            include_done: Whether to include completed points

        Returns:
            List of talking points ordered by sort_order
        """
        query = self.supabase.table("talking_points") \
            .select("*") \
            .eq("appointment_id", appointment_id)

        if not include_done:
            query = query.eq("done", False)

        result = query.order("sort_order").execute()

        return result.data or []

    async def update_talking_point(
        self,
        point_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update a talking point's text, category, or priority.

        Args:
            point_id: UUID of the talking point
            updates: Dictionary of fields to update

        Returns:
            Updated talking point record
        """
        # Filter to only allowed fields
        allowed_fields = {"text", "category", "priority"}
        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

        if not filtered_updates:
            return await self.get_talking_point(point_id)

        result = self.supabase.table("talking_points") \
            .update(filtered_updates) \
            .eq("id", point_id) \
            .execute()

        if result.data:
            return result.data[0]
        return None

    async def toggle_done(self, point_id: str) -> Optional[Dict[str, Any]]:
        """
        Toggle the done status of a talking point.

        Args:
            point_id: UUID of the talking point

        Returns:
            Updated talking point record
        """
        # Get current state
        current = await self.get_talking_point(point_id)
        if not current:
            return None

        new_done = not current["done"]
        checked_at = datetime.utcnow().isoformat() if new_done else None

        result = self.supabase.table("talking_points") \
            .update({
                "done": new_done,
                "checked_at": checked_at
            }) \
            .eq("id", point_id) \
            .execute()

        if result.data:
            print(f"Toggled talking point {point_id} to done={new_done}")
            return result.data[0]
        return None

    async def set_done(
        self,
        point_id: str,
        done: bool
    ) -> Optional[Dict[str, Any]]:
        """
        Explicitly set the done status of a talking point.

        Args:
            point_id: UUID of the talking point
            done: New done status

        Returns:
            Updated talking point record
        """
        checked_at = datetime.utcnow().isoformat() if done else None

        result = self.supabase.table("talking_points") \
            .update({
                "done": done,
                "checked_at": checked_at
            }) \
            .eq("id", point_id) \
            .execute()

        if result.data:
            return result.data[0]
        return None

    async def reorder_talking_points(
        self,
        appointment_id: str,
        point_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Reorder talking points for an appointment.

        Args:
            appointment_id: UUID of the appointment
            point_ids: List of point IDs in the desired order

        Returns:
            List of updated talking points
        """
        updated_points = []

        for index, point_id in enumerate(point_ids):
            result = self.supabase.table("talking_points") \
                .update({"sort_order": index}) \
                .eq("id", point_id) \
                .eq("appointment_id", appointment_id) \
                .execute()

            if result.data:
                updated_points.append(result.data[0])

        print(f"Reordered {len(updated_points)} talking points for appointment {appointment_id}")
        return updated_points

    async def delete_talking_point(self, point_id: str) -> bool:
        """
        Delete a talking point.

        Args:
            point_id: UUID of the talking point

        Returns:
            True if deleted successfully
        """
        self.supabase.table("talking_points") \
            .delete() \
            .eq("id", point_id) \
            .execute()

        print(f"Deleted talking point: {point_id}")
        return True

    async def bulk_create_talking_points(
        self,
        appointment_id: str,
        points: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Create multiple talking points at once.

        Args:
            appointment_id: UUID of the appointment
            points: List of point data dicts with text, category, priority

        Returns:
            List of created talking points
        """
        # Get current max sort_order
        result = self.supabase.table("talking_points") \
            .select("sort_order") \
            .eq("appointment_id", appointment_id) \
            .order("sort_order", desc=True) \
            .limit(1) \
            .execute()

        start_order = 0
        if result.data:
            start_order = (result.data[0]["sort_order"] or 0) + 1

        # Prepare batch insert data
        insert_data = []
        for i, point in enumerate(points):
            insert_data.append({
                "appointment_id": appointment_id,
                "text": point.get("text", ""),
                "category": point.get("category", "general"),
                "priority": point.get("priority", "medium"),
                "sort_order": start_order + i,
                "done": False
            })

        result = self.supabase.table("talking_points").insert(insert_data).execute()

        print(f"Created {len(result.data)} talking points for appointment {appointment_id}")
        return result.data or []

    async def get_unchecked_count(self, appointment_id: str) -> int:
        """
        Get the count of unchecked talking points for an appointment.

        Args:
            appointment_id: UUID of the appointment

        Returns:
            Number of unchecked points
        """
        result = self.supabase.table("talking_points") \
            .select("id", count="exact") \
            .eq("appointment_id", appointment_id) \
            .eq("done", False) \
            .execute()

        return result.count or 0

    async def get_talking_points_by_entry(
        self,
        entry_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get talking points for an appointment linked to a journal entry.
        Used to show talking points in the journal entry view.

        Args:
            entry_id: ID of the journal entry

        Returns:
            List of talking points from the linked appointment
        """
        # First, find the appointment linked to this entry
        appt_result = self.supabase.table("appointments") \
            .select("id") \
            .eq("linked_entry_id", entry_id) \
            .execute()

        if not appt_result.data:
            return []

        appointment_id = appt_result.data[0]["id"]

        # Then get the talking points
        points_result = self.supabase.table("talking_points") \
            .select("*") \
            .eq("appointment_id", appointment_id) \
            .order("sort_order") \
            .execute()

        return points_result.data or []
