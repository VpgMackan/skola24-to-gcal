"""
schedule_fetcher.py - High-level schedule fetching with caching.

Orchestrates the Skola24 API calls to fetch a complete schedule for a
given selection (class, teacher, student, room) and caches the results.
"""

import logging
import time
from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Optional, Dict, List, Tuple, Any

import skola24_api
import ics_generator

logger = logging.getLogger(__name__)

STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")


class ScheduleFetcher:
    """Fetches and caches Skola24 schedule data, serving it as ICS."""

    def __init__(
        self,
        host: str,
        unit_guid: str,
        selection_name: str,
        selection_type: int = skola24_api.SELECTION_TYPE_CLASS,
        weeks_ahead: int = 4,
        weeks_behind: int = 1,
        cache_ttl: int = 60,
        calendar_name: str = "",
        color_theme: str = "purple",
    ):
        """
        Initialize the schedule fetcher.

        Args:
            host: Skola24 host domain (e.g., "it-gymnasiet.skola24.se")
            unit_guid: School unit GUID
            selection_name: Human-readable name (class name, teacher ID, room name, or personnummer)
            selection_type: 0=class, 7=teacher, 5=room, 4=personal/student
            weeks_ahead: Number of weeks ahead to fetch
            weeks_behind: Number of weeks behind to fetch
            cache_ttl: Cache time-to-live in seconds
            calendar_name: Display name for the calendar
            color_theme: Pastel color theme base (green, purple, red)
        """
        self.host = host
        self.unit_guid = unit_guid
        self.selection_name = selection_name
        self.selection_type = selection_type
        self.weeks_ahead = weeks_ahead
        self.weeks_behind = weeks_behind
        self.cache_ttl = cache_ttl
        self.calendar_name = calendar_name or f"Skola24 - {selection_name}"
        self.color_theme = color_theme

        self._cached_ics: Optional[str] = None
        self._cache_time: float = 0.0
        self._selection_guid: Optional[str] = None
        self._school_year_guid: Optional[str] = None
        self._initialized: bool = False

    def _initialize(self):
        """Resolve selection name to GUID and get school year."""
        if self._initialized:
            return

        # Get school year
        logger.info(
            "Getting active school years for %s / %s", self.host, self.unit_guid
        )
        school_years = skola24_api.get_active_school_years(self.host, self.unit_guid)
        if school_years:
            self._school_year_guid = school_years[0]["guid"]
            logger.info(
                "Using school year: %s (%s)",
                school_years[0].get("name"),
                self._school_year_guid,
            )
        else:
            # Some schools don't require school year - try without
            logger.warning("No active school years found, will try without")
            self._school_year_guid = ""

        # Resolve selection name to GUID
        logger.info(
            "Resolving selection '%s' (type %d)",
            self.selection_name,
            self.selection_type,
        )
        self._selection_guid = skola24_api.resolve_selection(
            self.host, self.unit_guid, self.selection_name, self.selection_type
        )
        logger.info("Resolved selection GUID: %s", self._selection_guid[:20] + "...")

        self._initialized = True

    def _get_weeks_to_fetch(self) -> List[Tuple[int, int]]:
        """Calculate which (year, week) pairs to fetch."""
        now = datetime.now(STOCKHOLM_TZ)
        current_year, current_week, _ = now.isocalendar()

        weeks = []
        for offset in range(-self.weeks_behind, self.weeks_ahead + 1):
            target_week = current_week + offset
            target_year = current_year

            # Handle year boundaries
            while target_week < 1:
                target_year -= 1
                dec28 = date(target_year, 12, 28)
                max_week = dec28.isocalendar()[1]
                target_week += max_week

            while True:
                dec28 = date(target_year, 12, 28)
                max_week = dec28.isocalendar()[1]
                if target_week <= max_week:
                    break
                target_week -= max_week
                target_year += 1

            weeks.append((target_year, target_week))

        return weeks

    def fetch_schedule(self) -> Dict[Tuple[int, int], List[Dict[str, Any]]]:
        """
        Fetch the schedule for all configured weeks.

        Returns:
            Dict mapping (year, week) tuples to lists of lessons
        """
        self._initialize()
        weeks_to_fetch = self._get_weeks_to_fetch()
        all_lessons = {}

        for year, week in weeks_to_fetch:
            try:
                logger.debug("Fetching week %d of %d...", week, year)
                lessons = skola24_api.get_timetable(
                    host=self.host,
                    unit_guid=self.unit_guid,
                    selection=self._selection_guid,
                    week=week,
                    year=year,
                    selection_type=self.selection_type,
                    school_year=self._school_year_guid,
                )
                all_lessons[(year, week)] = lessons
                logger.debug("Week %d/%d: %d lessons", week, year, len(lessons))
            except Exception as e:
                logger.warning("Failed to fetch week %d/%d: %s", week, year, e)
                all_lessons[(year, week)] = []

        return all_lessons

    def get_ics(self, force_refresh: bool = False) -> str:
        """
        Get the ICS calendar data, using cache if available.

        Args:
            force_refresh: If True, bypass the cache

        Returns:
            ICS calendar string
        """
        now = time.time()

        if (
            not force_refresh
            and self._cached_ics is not None
            and (now - self._cache_time) < self.cache_ttl
        ):
            logger.debug("Serving cached ICS (age: %.0fs)", now - self._cache_time)
            return self._cached_ics

        logger.info("Fetching fresh schedule data...")
        try:
            lessons_by_week = self.fetch_schedule()
            self._cached_ics = ics_generator.lessons_to_ics(
                lessons_by_week,
                calendar_name=self.calendar_name,
                selection_name=self.selection_name,
                color_theme=self.color_theme,
            )
            self._cache_time = now
            logger.info("Schedule refreshed successfully")
        except Exception as e:
            logger.error("Failed to refresh schedule: %s", e)
            if self._cached_ics is not None:
                logger.info("Serving stale cached ICS")
            else:
                raise

        return self._cached_ics

    def invalidate_cache(self):
        """Force the next request to fetch fresh data."""
        self._cache_time = 0

    def reinitialize(self):
        """Force re-initialization (e.g., after school year change)."""
        self._initialized = False
        self._selection_guid = None
        self._school_year_guid = None
        self.invalidate_cache()
