"""
skola24_api.py - Skola24 API client for fetching timetable data.

This module handles all communication with the Skola24 API, including:
- Fetching available schools/units for a given host
- Getting render keys
- Getting active school years
- Fetching timetable lesson data for a given week
- Listing available classes, teachers, rooms, and groups

Selection Types (verified from web UI):
- 0 = class (uses groupGuid from classes list)
- 7 = teacher (uses personGuid from teachers list)
- 5 = room (uses eid from rooms list)
- 4 = personal/student (uses encrypted personnummer)
"""

import requests
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

BASE_URL = "https://web.skola24.se/api"

# This X-Scope value is used by the Skola24 web client and is required for API access
X_SCOPE = "8a22163c-8662-4535-9050-bc5e1923df48"

# Selection Types (verified from web UI):
SELECTION_TYPE_CLASS = 0
SELECTION_TYPE_PERSONAL = 4
SELECTION_TYPE_ROOM = 5
SELECTION_TYPE_TEACHER = 7


def _get_headers(host: str = "") -> Dict[str, str]:
    """Build the required headers for Skola24 API requests."""
    headers = {
        "Content-Type": "application/json",
        "X-Scope": X_SCOPE,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://web.skola24.se",
        "Referer": "https://web.skola24.se/",
    }
    if host:
        headers["Referer"] = (
            f"https://web.skola24.se/timetable/timetable-viewer/{host}/"
        )
    return headers


def _post(endpoint: str, data: Dict[str, Any], host: str = "") -> Dict[str, Any]:
    """Make a POST request to the Skola24 API."""
    url = f"{BASE_URL}/{endpoint}"
    headers = _get_headers(host)
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if result.get("error"):
            logger.error("Skola24 API error: %s", result.get("error"))
        if result.get("validation"):
            for v in result["validation"]:
                logger.warning("Skola24 validation: [%s] %s", v.get("code"), v.get("message"))
        return result
    except requests.RequestException as e:
        logger.error("Request to %s failed: %s", url, e)
        raise


def get_render_key(host: str = "") -> str:
    """Get a render key required for timetable rendering."""
    result = _post("get/timetable/render/key", {}, host)
    key = result.get("data", {}).get("key", "")
    if not key:
        raise ValueError("Failed to get render key from Skola24")
    return key


def encrypt_signature(signature: str, host: str = "") -> str:
    """Encrypt a selection identifier (used for personal/student timetables with personnummer)."""
    result = _post("encrypt/signature", {"signature": signature}, host)
    encrypted = result.get("data", {}).get("signature", "")
    if not encrypted:
        raise ValueError(f"Failed to encrypt signature for: {signature}")
    return encrypted


def get_units(host: str) -> List[Dict[str, Any]]:
    """Get all school units for a given Skola24 host domain."""
    result = _post(
        "services/skola24/get/timetable/viewer/units",
        {"getTimetableViewerUnitsRequest": {"hostName": host}},
        host,
    )
    units = (
        result.get("data", {})
        .get("getTimetableViewerUnitsResponse", {})
        .get("units", [])
    )
    return units


def get_active_school_years(host: str, unit_guid: str = "") -> List[Dict[str, Any]]:
    """
    Get active school years for a given host and optionally a specific unit.
    
    Note: The unitGuid parameter is required for some schools to return results.
    """
    body = {
        "hostName": host,
        "checkSchoolYearsFeatures": True,
    }
    if unit_guid:
        body["unitGuid"] = unit_guid
    else:
        body["getTimetableViewerUnitsRequest"] = {"hostName": host}

    result = _post("get/active/school/years", body, host)
    return result.get("data", {}).get("activeSchoolYears", [])


def _build_selection_filters(
    class_filter: bool = False,
    course_filter: bool = False,
    group_filter: bool = False,
    period_filter: bool = False,
    room_filter: bool = False,
    student_filter: bool = False,
    subject_filter: bool = False,
    teacher_filter: bool = False,
) -> Dict[str, bool]:
    return {
        "class": class_filter,
        "course": course_filter,
        "group": group_filter,
        "period": period_filter,
        "room": room_filter,
        "student": student_filter,
        "subject": subject_filter,
        "teacher": teacher_filter,
    }

def get_selection(
    host: str,
    unit_guid: str,
    filters: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """
    Get available selections (classes, teachers, rooms, etc.) for a school unit.
    """
    if filters is None:
        filters = _build_selection_filters(class_filter=True)
    result = _post(
        "get/timetable/selection",
        {"hostName": host, "unitGuid": unit_guid, "filters": filters},
        host,
    )
    return result.get("data", {})


def get_timetable(
    host: str,
    unit_guid: str,
    selection: str,
    week: int,
    year: int,
    selection_type: int = SELECTION_TYPE_CLASS,
    schedule_day: int = 0,
    school_year: str = "",
    width: int = 1223,
    height: int = 832,
) -> List[Dict[str, Any]]:
    """
    Fetch timetable lesson data for a specific week.

    Args:
        host: Skola24 host domain (e.g., "it-gymnasiet.skola24.se")
        unit_guid: The school unit GUID
        selection: The selection GUID:
                   - For classes: groupGuid from list_classes()
                   - For teachers: personGuid from list_teachers()
                   - For rooms: eid from list_rooms()
                   - For personal: encrypted personnummer from encrypt_signature()
        week: Week number (1-53)
        year: Year
        selection_type: 0=class, 7=teacher, 5=room, 4=personal/student
        schedule_day: 0 = whole week, 1-5 = specific day
        school_year: School year GUID (from get_active_school_years)
        width: Render width
        height: Render height

    Returns:
        List of lesson info dictionaries
    """
    render_key = get_render_key(host)

    request_data = {
        "renderKey": render_key,
        "host": host,
        "unitGuid": unit_guid,
        "schoolYear": school_year,
        "startDate": None,
        "endDate": None,
        "scheduleDay": schedule_day,
        "blackAndWhite": False,
        "width": width,
        "height": height,
        "selectionType": selection_type,
        "selection": selection,
        "showHeader": False,
        "periodText": "",
        "week": week,
        "year": year,
        "privateFreeTextMode": None,
        "privateSelectionMode": False,
        "customerKey": "",
        "personalTimetable": False,
    }

    result = _post("render/timetable", request_data, host)
    lessons = result.get("data", {}).get("lessonInfo", [])
    return lessons if lessons is not None else []


def list_classes(host: str, unit_guid: str) -> List[Dict[str, Any]]:
    """
    List all available classes for a school unit.
    
    Returns list of dicts with keys: groupGuid, groupName, selectableBy
    Use groupGuid as 'selection' with selectionType=0
    """
    data = get_selection(host, unit_guid, filters=_build_selection_filters(class_filter=True))
    return data.get("classes", [])


def list_teachers(host: str, unit_guid: str) -> List[Dict[str, Any]]:
    """
    List all available teachers for a school unit.
    
    Returns list of dicts with keys: fullName, id, integrity, personGuid, selectableBy
    Use personGuid as 'selection' with selectionType=7
    """
    data = get_selection(host, unit_guid, filters=_build_selection_filters(teacher_filter=True))
    return data.get("teachers", [])


def list_rooms(host: str, unit_guid: str) -> List[Dict[str, Any]]:
    """
    List all available rooms for a school unit.
    
    Returns list of dicts with keys: id, name, eid, external, selectableBy
    Use eid as 'selection' with selectionType=5
    """
    data = get_selection(host, unit_guid, filters=_build_selection_filters(room_filter=True))
    return data.get("rooms", [])


def list_groups(host: str, unit_guid: str) -> List[Dict[str, Any]]:
    """List all available groups for a school unit."""
    data = get_selection(host, unit_guid, filters=_build_selection_filters(group_filter=True))
    return data.get("groups", [])


def resolve_selection(
    host: str,
    unit_guid: str,
    selection_name: str,
    selection_type: int,
) -> str:
    """
    Resolve a human-readable selection name to the GUID needed for the API.
    
    Args:
        host: Skola24 host domain
        unit_guid: School unit GUID
        selection_name: Human-readable name (class name, teacher ID, room name, or personnummer)
        selection_type: 0=class, 7=teacher, 5=room, 4=personal
        
    Returns:
        The GUID to use as 'selection' in get_timetable()
    """
    if selection_type == SELECTION_TYPE_CLASS:
        # Class - look up by groupName
        classes = list_classes(host, unit_guid)
        for cls in classes:
            if cls.get("groupName", "").lower() == selection_name.lower():
                return cls["groupGuid"]
        # Try partial match
        for cls in classes:
            if selection_name.lower() in cls.get("groupName", "").lower():
                logger.info("Partial match: '%s' -> '%s'", selection_name, cls["groupName"])
                return cls["groupGuid"]
        raise ValueError(
            f"Class '{selection_name}' not found. Available: "
            + ", ".join(c["groupName"] for c in classes[:20])
        )
    
    elif selection_type == SELECTION_TYPE_TEACHER:
        # Teacher - look up by ID or name
        teachers = list_teachers(host, unit_guid)
        for t in teachers:
            if t.get("id", "").lower() == selection_name.lower():
                return t["personGuid"]
        for t in teachers:
            if selection_name.lower() in t.get("fullName", "").lower():
                logger.info("Partial match: '%s' -> '%s'", selection_name, t["fullName"])
                return t["personGuid"]
        raise ValueError(
            f"Teacher '{selection_name}' not found. Available: "
            + ", ".join(f"{t['id']} ({t.get('fullName','')})" for t in teachers[:20])
        )
    
    elif selection_type == SELECTION_TYPE_ROOM:
        # Room - look up by name
        rooms = list_rooms(host, unit_guid)
        for r in rooms:
            if r.get("name", "").lower() == selection_name.lower():
                return r["eid"]
        raise ValueError(
            f"Room '{selection_name}' not found. Available: "
            + ", ".join(r["name"] for r in rooms[:20])
        )
    
    elif selection_type == SELECTION_TYPE_PERSONAL:
        # Personal/student - encrypt the personnummer
        return encrypt_signature(selection_name, host)
    
    else:
        raise ValueError(f"Unknown selection type: {selection_type}")
