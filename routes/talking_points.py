# routes/talking_points.py
"""
API endpoints for talking points (checklist items) management.
Handles CRUD, toggle, and reorder operations.
"""

from fastapi import APIRouter, HTTPException, Form
from typing import Optional, List
from pydantic import BaseModel
from services.talking_points_service import TalkingPointsService
from services.database_service import database_service

router = APIRouter()

# Initialize service with the database client
talking_points_service = TalkingPointsService(database_service.supabase)


class ReorderRequest(BaseModel):
    """Request body for reordering talking points"""
    appointment_id: str
    point_ids: List[str]


class BulkCreateRequest(BaseModel):
    """Request body for bulk creating talking points"""
    appointment_id: str
    points: List[dict]


@router.post("/create")
async def create_talking_point(
    appointment_id: str = Form(...),
    text: str = Form(...),
    category: str = Form("general"),
    priority: str = Form("medium")
):
    """
    Create a new talking point for an appointment.

    Form fields:
    - appointment_id: UUID of the parent appointment (required)
    - text: The talking point text (required)
    - category: Category (medication, symptoms, results, questions, general) (default: general)
    - priority: Priority level (high, medium, low) (default: medium)
    """
    # Validate category
    valid_categories = {"medication", "symptoms", "results", "questions", "general"}
    if category not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Category must be one of: {', '.join(valid_categories)}"
        )

    # Validate priority
    valid_priorities = {"high", "medium", "low"}
    if priority not in valid_priorities:
        raise HTTPException(
            status_code=400,
            detail=f"Priority must be one of: {', '.join(valid_priorities)}"
        )

    try:
        point = await talking_points_service.create_talking_point(
            appointment_id=appointment_id,
            text=text,
            category=category,
            priority=priority
        )
        return {
            "success": True,
            "talking_point": point
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-create")
async def bulk_create_talking_points(request: BulkCreateRequest):
    """
    Create multiple talking points at once.

    Request body:
    - appointment_id: UUID of the appointment
    - points: Array of point objects with text, category (optional), priority (optional)
    """
    try:
        points = await talking_points_service.bulk_create_talking_points(
            appointment_id=request.appointment_id,
            points=request.points
        )
        return {
            "success": True,
            "talking_points": points,
            "count": len(points)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/appointment/{appointment_id}")
async def list_talking_points(
    appointment_id: str,
    include_done: bool = True
):
    """
    List all talking points for an appointment.

    Path parameters:
    - appointment_id: UUID of the appointment

    Query parameters:
    - include_done: Whether to include completed points (default: true)
    """
    try:
        points = await talking_points_service.list_talking_points(
            appointment_id=appointment_id,
            include_done=include_done
        )
        return {
            "success": True,
            "talking_points": points,
            "count": len(points)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entry/{entry_id}")
async def get_talking_points_by_entry(entry_id: str):
    """
    Get talking points for an appointment linked to a journal entry.
    Used to display talking points in the journal entry view.

    Path parameters:
    - entry_id: ID of the journal entry
    """
    try:
        points = await talking_points_service.get_talking_points_by_entry(entry_id)
        return {
            "success": True,
            "talking_points": points,
            "count": len(points)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{point_id}")
async def get_talking_point(point_id: str):
    """
    Get a single talking point by ID.

    Path parameters:
    - point_id: UUID of the talking point
    """
    try:
        point = await talking_points_service.get_talking_point(point_id)
        if not point:
            raise HTTPException(status_code=404, detail="Talking point not found")

        return {
            "success": True,
            "talking_point": point
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{point_id}")
async def update_talking_point(
    point_id: str,
    text: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    priority: Optional[str] = Form(None)
):
    """
    Update a talking point's text, category, or priority.

    Path parameters:
    - point_id: UUID of the talking point

    Form fields (all optional):
    - text: New text
    - category: New category (medication, symptoms, results, questions, general)
    - priority: New priority (high, medium, low)
    """
    updates = {}

    if text is not None:
        updates["text"] = text

    if category is not None:
        valid_categories = {"medication", "symptoms", "results", "questions", "general"}
        if category not in valid_categories:
            raise HTTPException(
                status_code=400,
                detail=f"Category must be one of: {', '.join(valid_categories)}"
            )
        updates["category"] = category

    if priority is not None:
        valid_priorities = {"high", "medium", "low"}
        if priority not in valid_priorities:
            raise HTTPException(
                status_code=400,
                detail=f"Priority must be one of: {', '.join(valid_priorities)}"
            )
        updates["priority"] = priority

    try:
        point = await talking_points_service.update_talking_point(
            point_id=point_id,
            updates=updates
        )
        if not point:
            raise HTTPException(status_code=404, detail="Talking point not found")

        return {
            "success": True,
            "talking_point": point
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{point_id}/toggle")
async def toggle_done(point_id: str):
    """
    Toggle the done status of a talking point.

    Path parameters:
    - point_id: UUID of the talking point
    """
    try:
        point = await talking_points_service.toggle_done(point_id)
        if not point:
            raise HTTPException(status_code=404, detail="Talking point not found")

        return {
            "success": True,
            "talking_point": point,
            "done": point["done"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{point_id}/done")
async def set_done_status(
    point_id: str,
    done: bool = Form(...)
):
    """
    Explicitly set the done status of a talking point.

    Path parameters:
    - point_id: UUID of the talking point

    Form fields:
    - done: Boolean value for done status (required)
    """
    try:
        point = await talking_points_service.set_done(
            point_id=point_id,
            done=done
        )
        if not point:
            raise HTTPException(status_code=404, detail="Talking point not found")

        return {
            "success": True,
            "talking_point": point,
            "done": point["done"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reorder")
async def reorder_talking_points(request: ReorderRequest):
    """
    Reorder talking points for an appointment.

    Request body:
    - appointment_id: UUID of the appointment
    - point_ids: List of point IDs in the desired order
    """
    try:
        points = await talking_points_service.reorder_talking_points(
            appointment_id=request.appointment_id,
            point_ids=request.point_ids
        )
        return {
            "success": True,
            "talking_points": points,
            "count": len(points)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{point_id}")
async def delete_talking_point(point_id: str):
    """
    Delete a talking point.

    Path parameters:
    - point_id: UUID of the talking point
    """
    try:
        await talking_points_service.delete_talking_point(point_id)
        return {
            "success": True,
            "message": f"Talking point {point_id} deleted"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/appointment/{appointment_id}/unchecked-count")
async def get_unchecked_count(appointment_id: str):
    """
    Get the count of unchecked talking points for an appointment.

    Path parameters:
    - appointment_id: UUID of the appointment
    """
    try:
        count = await talking_points_service.get_unchecked_count(appointment_id)
        return {
            "success": True,
            "appointment_id": appointment_id,
            "unchecked_count": count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
