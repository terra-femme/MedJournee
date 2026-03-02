# routes/appointments.py
"""
API endpoints for appointment management.
Handles CRUD operations and linking to journal entries.
"""

from fastapi import APIRouter, HTTPException, Form
from typing import Optional
from services.appointments_service import AppointmentsService
from services.database_service import database_service

router = APIRouter()

# Initialize service with the database client
appointments_service = AppointmentsService(database_service.supabase)


@router.post("/create")
async def create_appointment(
    user_id: str = Form(...),
    family_id: str = Form(...),
    scheduled_date: str = Form(...),
    title: Optional[str] = Form(None),
    scheduled_time: Optional[str] = Form(None),
    provider_name: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    appointment_type: Optional[str] = Form(None)
):
    """
    Create a new appointment.

    Form fields:
    - user_id: User identifier (required)
    - family_id: Family group identifier (required)
    - scheduled_date: Date in YYYY-MM-DD format (required)
    - title: Appointment title (optional, defaults to "Appointment")
    - scheduled_time: Time in HH:MM format (optional)
    - provider_name: Healthcare provider name (optional)
    - location: Appointment location (optional)
    - appointment_type: Type (checkup, follow-up, lab, imaging, specialist) (optional)
    """
    # Default title if not provided
    appointment_title = title if title else "Appointment"

    try:
        appointment = await appointments_service.create_appointment(
            user_id=user_id,
            family_id=family_id,
            title=appointment_title,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            provider_name=provider_name,
            location=location,
            appointment_type=appointment_type
        )
        return {
            "success": True,
            "appointment": appointment
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list/{user_id}")
async def list_appointments(
    user_id: str,
    status: Optional[str] = None,
    limit: int = 50
):
    """
    List all appointments for a user.

    Path parameters:
    - user_id: User identifier

    Query parameters:
    - status: Filter by status (scheduled, completed, cancelled)
    - limit: Maximum number of results (default 50)
    """
    try:
        appointments = await appointments_service.list_appointments(
            user_id=user_id,
            status=status,
            limit=limit
        )
        return {
            "success": True,
            "appointments": appointments,
            "count": len(appointments)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/month/{user_id}/{year}/{month}")
async def get_appointments_for_month(
    user_id: str,
    year: int,
    month: int
):
    """
    Get appointments for a specific calendar month.

    Path parameters:
    - user_id: User identifier
    - year: Year (e.g., 2026)
    - month: Month (1-12)
    """
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Month must be between 1 and 12")

    try:
        appointments = await appointments_service.get_appointments_for_month(
            user_id=user_id,
            year=year,
            month=month
        )

        # Create a map of dates that have appointments
        dates_with_appointments = {}
        for appt in appointments:
            date_str = appt["scheduled_date"]
            if date_str not in dates_with_appointments:
                dates_with_appointments[date_str] = []
            dates_with_appointments[date_str].append({
                "id": appt["id"],
                "title": appt["title"],
                "time": appt["scheduled_time"],
                "provider": appt.get("provider_name"),
                "status": appt["status"]
            })

        return {
            "success": True,
            "year": year,
            "month": month,
            "appointments": appointments,
            "dates_with_appointments": dates_with_appointments,
            "count": len(appointments)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/upcoming/{user_id}")
async def get_upcoming_appointments(
    user_id: str,
    limit: int = 5
):
    """
    Get upcoming scheduled appointments.

    Path parameters:
    - user_id: User identifier

    Query parameters:
    - limit: Maximum number of results (default 5)
    """
    try:
        appointments = await appointments_service.get_upcoming_appointments(
            user_id=user_id,
            limit=limit
        )
        return {
            "success": True,
            "appointments": appointments,
            "count": len(appointments)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/past-unlinked/{user_id}")
async def get_past_unlinked_appointments(
    user_id: str,
    limit: int = 10
):
    """
    Get past appointments without linked journal entries.

    Path parameters:
    - user_id: User identifier

    Query parameters:
    - limit: Maximum number of results (default 10)
    """
    try:
        appointments = await appointments_service.get_unlinked_past_appointments(
            user_id=user_id,
            limit=limit
        )
        return {
            "success": True,
            "appointments": appointments,
            "count": len(appointments)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/date/{user_id}/{date}")
async def get_appointments_for_date(
    user_id: str,
    date: str
):
    """
    Get all appointments for a specific date.

    Path parameters:
    - user_id: User identifier
    - date: Date in YYYY-MM-DD format
    """
    try:
        appointments = await appointments_service.get_appointments_for_date(
            user_id=user_id,
            target_date=date
        )
        return {
            "success": True,
            "date": date,
            "appointments": appointments,
            "count": len(appointments)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{appointment_id}")
async def get_appointment(appointment_id: str):
    """
    Get a single appointment by ID with its talking points.

    Path parameters:
    - appointment_id: UUID of the appointment
    """
    try:
        appointment = await appointments_service.get_appointment(appointment_id)
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        return {
            "success": True,
            "appointment": appointment
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{appointment_id}")
async def update_appointment(
    appointment_id: str,
    title: Optional[str] = Form(None),
    scheduled_date: Optional[str] = Form(None),
    scheduled_time: Optional[str] = Form(None),
    provider_name: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    appointment_type: Optional[str] = Form(None),
    status: Optional[str] = Form(None)
):
    """
    Update an appointment.

    Path parameters:
    - appointment_id: UUID of the appointment

    Form fields (all optional):
    - title: New title
    - scheduled_date: New date
    - scheduled_time: New time
    - provider_name: New provider name
    - location: New location
    - appointment_type: New type
    - status: New status (scheduled, completed, cancelled)
    """
    updates = {}
    if title is not None:
        updates["title"] = title
    if scheduled_date is not None:
        updates["scheduled_date"] = scheduled_date
    if scheduled_time is not None:
        updates["scheduled_time"] = scheduled_time
    if provider_name is not None:
        updates["provider_name"] = provider_name
    if location is not None:
        updates["location"] = location
    if appointment_type is not None:
        updates["appointment_type"] = appointment_type
    if status is not None:
        if status not in ("scheduled", "completed", "cancelled"):
            raise HTTPException(
                status_code=400,
                detail="Status must be 'scheduled', 'completed', or 'cancelled'"
            )
        updates["status"] = status

    try:
        appointment = await appointments_service.update_appointment(
            appointment_id=appointment_id,
            updates=updates
        )
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        return {
            "success": True,
            "appointment": appointment
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{appointment_id}")
async def delete_appointment(appointment_id: str):
    """
    Delete an appointment. This also deletes all associated talking points.

    Path parameters:
    - appointment_id: UUID of the appointment
    """
    try:
        await appointments_service.delete_appointment(appointment_id)
        return {
            "success": True,
            "message": f"Appointment {appointment_id} deleted"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{appointment_id}/link/{entry_id}")
async def link_to_journal_entry(
    appointment_id: str,
    entry_id: str
):
    """
    Link an appointment to a journal entry after a visit.
    This also marks the appointment as completed.

    Path parameters:
    - appointment_id: UUID of the appointment
    - entry_id: ID of the journal entry
    """
    try:
        appointment = await appointments_service.link_to_journal_entry(
            appointment_id=appointment_id,
            entry_id=entry_id
        )
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        return {
            "success": True,
            "message": "Appointment linked to journal entry",
            "appointment": appointment
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{appointment_id}/unlink")
async def unlink_journal_entry(appointment_id: str):
    """
    Remove the link between an appointment and its journal entry.

    Path parameters:
    - appointment_id: UUID of the appointment
    """
    try:
        appointment = await appointments_service.unlink_journal_entry(appointment_id)
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        return {
            "success": True,
            "message": "Journal entry unlinked",
            "appointment": appointment
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
