"""
ics_generator.py - Generate ICS calendar files from Skola24 lesson data.

Converts Skola24 timetable lesson data into standard iCalendar (ICS) format
that can be imported into Google Calendar, Apple Calendar, Outlook, etc.
"""

import hashlib
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Tuple, Any

logger = logging.getLogger(__name__)

STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")
UTC_TZ = ZoneInfo("UTC")

BASE_THEME_COLORS = {
    "green": "#4CAF50",
    "purple": "#9C27B0",
    "red": "#E53935",
}

THEME_ALIASES = {
    "purble": "purple",
    "violet": "purple",
}


def _escape_ics_text(text: str) -> str:
    """Escape special characters for ICS format."""
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text


def _format_datetime_utc(dt: datetime) -> str:
    """Format a datetime as ICS UTC timestamp (YYYYMMDDTHHmmssZ)."""
    utc_dt = dt.astimezone(UTC_TZ)
    return utc_dt.strftime("%Y%m%dT%H%M%SZ")


def _get_week_start_date(year: int, week: int) -> datetime:
    """Get the Monday of a given ISO week."""
    # ISO week date: January 4th is always in week 1
    jan4 = datetime(year, 1, 4, tzinfo=STOCKHOLM_TZ)
    # Find Monday of week 1
    week1_monday = jan4 - timedelta(days=jan4.isoweekday() - 1)
    # Calculate target Monday
    target_monday = week1_monday + timedelta(weeks=week - 1)
    return target_monday


def _parse_time(time_str: str) -> Tuple[int, int, int]:
    """Parse a time string like '08:30:00' into (hour, minute, second)."""
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0


def _generate_uid(lesson: Dict[str, Any], date_str: str) -> str:
    """Generate a stable UID for a calendar event."""
    guid = lesson.get("guidId", "")
    if guid:
        return f"{guid}-{date_str}@skola24-sync"
    # Fallback: hash the lesson details
    raw = f"{date_str}-{lesson.get('timeStart','')}-{lesson.get('timeEnd','')}-{'-'.join(lesson.get('texts', []))}"
    return f"{hashlib.md5(raw.encode()).hexdigest()}@skola24-sync"


def _normalize_subject(subject: str) -> str:
    """Normalize a subject string for stable color mapping."""
    return " ".join((subject or "Lesson").strip().lower().split())


def _normalize_theme_name(theme_name: str) -> str:
    """Normalize and validate theme name, with aliases and fallback."""
    normalized = (theme_name or "purple").strip().lower()
    normalized = THEME_ALIASES.get(normalized, normalized)
    if normalized not in BASE_THEME_COLORS:
        return "purple"
    return normalized


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert #RRGGBB to (R, G, B)."""
    value = hex_color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert (R, G, B) to #RRGGBB."""
    return f"#{r:02X}{g:02X}{b:02X}"


def _mix_with_white(r: int, g: int, b: int, white_ratio: float) -> Tuple[int, int, int]:
    """Blend a color with white using white_ratio in [0, 1]."""
    mixed_r = round(r * (1 - white_ratio) + 255 * white_ratio)
    mixed_g = round(g * (1 - white_ratio) + 255 * white_ratio)
    mixed_b = round(b * (1 - white_ratio) + 255 * white_ratio)
    return mixed_r, mixed_g, mixed_b


def _build_theme_gradient(theme_name: str, steps: int = 14) -> List[str]:
    """Generate a soft pastel gradient from light to slightly deeper tones."""
    normalized_theme = _normalize_theme_name(theme_name)
    base_hex = BASE_THEME_COLORS[normalized_theme]
    base_r, base_g, base_b = _hex_to_rgb(base_hex)

    # Cute pastel range: mostly light shades
    max_white = 0.85
    min_white = 0.45
    if steps <= 1:
        steps = 1

    gradient = []
    for idx in range(steps):
        ratio = idx / (steps - 1) if steps > 1 else 0
        white_ratio = max_white - (max_white - min_white) * ratio
        r, g, b = _mix_with_white(base_r, base_g, base_b, white_ratio)
        gradient.append(_rgb_to_hex(r, g, b))

    return gradient


def _subject_color(subject: str, palette: List[str]) -> str:
    """Pick a deterministic pastel color for a subject from a palette."""
    normalized = _normalize_subject(subject)
    color_index = int(hashlib.md5(normalized.encode("utf-8")).hexdigest(), 16) % len(
        palette
    )
    return palette[color_index]


def lessons_to_ics(
    lessons_by_week: Dict[Tuple[int, int], List[Dict[str, Any]]],
    calendar_name: str = "Skola24 Schedule",
    selection_name: str = "",
    color_theme: str = "purple",
) -> str:
    """
    Convert Skola24 lesson data into an ICS calendar string.

    Args:
        lessons_by_week: Dict mapping (year, week) tuples to lists of lessons
        calendar_name: Name for the calendar
        selection_name: Name of the class/teacher/group for the calendar
        color_theme: Main color theme for pastel gradient (green, purple, red)

    Returns:
        ICS calendar string
    """
    now_utc = datetime.now(UTC_TZ).strftime("%Y%m%dT%H%M%SZ")
    palette = _build_theme_gradient(color_theme)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Skola24-to-GCal//Skola24 Schedule Sync//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape_ics_text(calendar_name)}",
        "X-WR-TIMEZONE:Europe/Stockholm",
        # Include VTIMEZONE for Europe/Stockholm
        "BEGIN:VTIMEZONE",
        "TZID:Europe/Stockholm",
        "BEGIN:STANDARD",
        "DTSTART:19701025T030000",
        "RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10",
        "TZOFFSETFROM:+0200",
        "TZOFFSETTO:+0100",
        "TZNAME:CET",
        "END:STANDARD",
        "BEGIN:DAYLIGHT",
        "DTSTART:19700329T020000",
        "RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3",
        "TZOFFSETFROM:+0100",
        "TZOFFSETTO:+0200",
        "TZNAME:CEST",
        "END:DAYLIGHT",
        "END:VTIMEZONE",
    ]

    event_count = 0

    for (year, week), lessons in sorted(lessons_by_week.items()):
        if not lessons:
            continue

        week_start = _get_week_start_date(year, week)

        for lesson in lessons:
            day_of_week: int = lesson.get("dayOfWeekNumber", 1)
            time_start: str = lesson.get("timeStart", "")
            time_end: str = lesson.get("timeEnd", "")
            texts: List[str] = lesson.get("texts", [])

            if not time_start or not time_end:
                continue

            # Calculate the actual date
            lesson_date = week_start + timedelta(days=day_of_week - 1)
            date_str = lesson_date.strftime("%Y-%m-%d")

            # Parse times
            sh, sm, ss = _parse_time(time_start)
            eh, em, es = _parse_time(time_end)

            start_dt = lesson_date.replace(hour=sh, minute=sm, second=ss)
            end_dt = lesson_date.replace(hour=eh, minute=em, second=es)

            # Build event details
            summary: str = texts[0] if texts else "Lesson"
            teacher: str = texts[1] if len(texts) > 1 else ""
            location: str = texts[2] if len(texts) > 2 else ""
            event_color: str = _subject_color(summary, palette)

            # Build description from all text fields
            description_parts = []
            if len(texts) > 0:
                description_parts.append(f"Subject: {texts[0]}")
            if len(texts) > 1:
                description_parts.append(f"Teacher: {texts[1]}")
            if len(texts) > 2:
                description_parts.append(f"Room: {texts[2]}")
            for i, t in enumerate(texts[3:], 3):
                description_parts.append(t)
            description = "\\n".join(description_parts)

            uid: str = _generate_uid(lesson, date_str)

            lines.append("BEGIN:VEVENT")
            lines.append(f"DTSTAMP:{now_utc}")
            lines.append(f"UID:{uid}")
            lines.append(
                f"DTSTART;TZID=Europe/Stockholm:{start_dt.strftime('%Y%m%dT%H%M%S')}"
            )
            lines.append(
                f"DTEND;TZID=Europe/Stockholm:{end_dt.strftime('%Y%m%dT%H%M%S')}"
            )
            lines.append(f"SUMMARY:{_escape_ics_text(summary)}")
            lines.append(f"COLOR:{event_color}")
            if location:
                lines.append(f"LOCATION:{_escape_ics_text(location)}")
            if description:
                lines.append(f"DESCRIPTION:{description}")
            if teacher:
                lines.append(f"X-SKOLA24-TEACHER:{_escape_ics_text(teacher)}")

            # Color coding based on lesson type
            guid_id: str = lesson.get("guidId", "")
            if guid_id:
                lines.append(f"X-SKOLA24-GUID:{guid_id}")

            lines.append("END:VEVENT")
            event_count += 1

    lines.append("END:VCALENDAR")

    logger.info("Generated ICS with %d events", event_count)
    return "\r\n".join(lines)
