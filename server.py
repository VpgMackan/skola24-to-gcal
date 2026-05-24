#!/usr/bin/env python3
"""
server.py - Main entry point for Skola24-to-GCal.

Provides:
1. An HTTP server that serves the schedule as an ICS feed
2. CLI commands for discovering schools, classes, and teachers
3. Quick config support via /user/schedule.ics paths

Usage:
    python3 server.py serve

    python3 server.py list-schools --host it-gymnasiet.skola24.se
    python3 server.py list-classes --host it-gymnasiet.skola24.se --unit-guid <GUID>
    python3 server.py init-config
"""

import argparse
import json
import logging
import sys
import os
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List

from config import load_config, validate_config, generate_example_config, config_from_url_params, DEFAULT_CONFIG
from schedule_fetcher import ScheduleFetcher

logger = logging.getLogger("skola24-to-gcal")

fetcher_cache: Dict[str, ScheduleFetcher] = {}


class ICSRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler that serves the ICS feed."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        if path in ("", "/", "/schedule", "/schedule.ics", "/calendar.ics"):
            self.send_error(404, "Not Found. Use a quick config path like /marnie/schedule.ics or provide URL parameters.")
        elif path.startswith("/refresh"):
            self._serve_refresh(query)
        elif path.startswith("/info"):
            self._serve_info(query)
        else:
            self._serve_quick_config(path, query)

    def _get_quick_config_name(self, path: str) -> Optional[str]:
        """Extract quick config name from path like /marnie/schedule.ics -> marnie"""
        parts = path.strip("/").split("/")
        if len(parts) >= 1 and parts[0]:
            return parts[0]
        return None

    def _get_or_create_fetcher(self, query: Dict[str, List[str]], quick_config: Optional[str] = None) -> Optional[ScheduleFetcher]:
        """Get or create a fetcher based on URL params or quick config."""
        config = None
        
        if quick_config:
            cache_key = f"quick:{quick_config}"
        elif query.get("user"):
            cache_key = hashlib.md5(query["user"][0].encode()).hexdigest()[:12]
        else:
            return None
        
        if cache_key in fetcher_cache:
            return fetcher_cache[cache_key]
        
        if quick_config:
            loaded = load_config()
            if quick_config in loaded.get("users", {}):
                raw = loaded["users"][quick_config]
                config = {
                    "skola24": {
                        "host": raw.get("host", ""),
                        "unit_guid": raw.get("unit_guid", ""),
                        "selection": raw.get("selection", ""),
                        "selection_type": raw.get("selection_type", 0),
                    },
                    "schedule": {
                        "weeks_ahead": raw.get("weeks_ahead", 4),
                        "weeks_behind": raw.get("weeks_behind", 1),
                        "cache_ttl": raw.get("cache_ttl", 60),
                        "calendar_name": raw.get("calendar_name", ""),
                        "color_theme": raw.get("color_theme", "purple"),
                    },
                }
            else:
                return None
        elif query.get("user"):
            raw = config_from_url_params(query)
            config = {
                "skola24": {
                    "host": raw.get("host", ""),
                    "unit_guid": raw.get("unit_guid", ""),
                    "selection": raw.get("selection", ""),
                    "selection_type": raw.get("selection_type", 0),
                },
                "schedule": {
                    "weeks_ahead": raw.get("weeks_ahead", 4),
                    "weeks_behind": raw.get("weeks_behind", 1),
                    "cache_ttl": raw.get("cache_ttl", 60),
                    "calendar_name": raw.get("calendar_name", ""),
                    "color_theme": raw.get("color_theme", "purple"),
                },
            }
        else:
            return None
        
        errors = validate_config(config)
        if errors:
            logger.warning("Config validation errors: %s", errors)
            return None
        
        sk = config["skola24"]
        sched = config["schedule"]
        
        fetcher = ScheduleFetcher(
            host=sk["host"],
            unit_guid=sk["unit_guid"],
            selection_name=sk["selection"],
            selection_type=sk["selection_type"],
            weeks_ahead=sched["weeks_ahead"],
            weeks_behind=sched.get("weeks_behind", 1),
            cache_ttl=sched["cache_ttl"],
            calendar_name=sched.get("calendar_name", ""),
            color_theme=sched.get("color_theme", "purple"),
        )
        fetcher_cache[cache_key] = fetcher
        return fetcher

    def _serve_health(self):
        """Health check endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode())

    def _serve_refresh(self, query: Dict[str, List[str]]):
        """Force refresh the schedule cache."""
        quick_config = self._get_quick_config_name(self.path)
        try:
            fetcher = self._get_or_create_fetcher(query, quick_config)
            if fetcher:
                fetcher.invalidate_cache()
                ics_data = fetcher.get_ics(force_refresh=True)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "status": "refreshed",
                            "events": ics_data.count("BEGIN:VEVENT"),
                        }
                    ).encode()
                )
            else:
                self.send_error(400, "Invalid configuration")
        except Exception as e:
            logger.error("Error refreshing: %s", e, exc_info=True)
            self.send_error(500, f"Refresh failed: {e}")

    def _serve_info(self, query: Dict[str, List[str]]):
        """Serve information about the current configuration."""
        quick_config = self._get_quick_config_name(self.path)
        fetcher = self._get_or_create_fetcher(query, quick_config)
        if not fetcher:
            self.send_error(400, "Invalid configuration. Provide host, unit_guid, and selection params.")
            return

        info = {
            "host": fetcher.host,
            "unit_guid": fetcher.unit_guid,
            "selection": fetcher.selection_name,
            "selection_type": fetcher.selection_type,
            "selection_type_label": {
                skola24_api.SELECTION_TYPE_CLASS: "class",
                skola24_api.SELECTION_TYPE_TEACHER: "teacher",
                skola24_api.SELECTION_TYPE_ROOM: "room",
                skola24_api.SELECTION_TYPE_PERSONAL: "personal",
            }.get(fetcher.selection_type, "unknown"),
            "weeks_ahead": fetcher.weeks_ahead,
            "weeks_behind": fetcher.weeks_behind,
            "cache_ttl": fetcher.cache_ttl,
            "calendar_name": fetcher.calendar_name,
            "color_theme": fetcher.color_theme,
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(info, indent=2).encode())

    def _serve_quick_config(self, path: str, query: Dict[str, List[str]]):
        """Serve ICS for a quick config path like /marnie/schedule.ics."""
        quick_config = self._get_quick_config_name(path)
        if not quick_config:
            self.send_error(404, "Not Found")
            return
        
        fetcher = self._get_or_create_fetcher(query, quick_config)
        if not fetcher:
            self.send_error(400, f"Quick config '{quick_config}' not found in config.yaml under 'users:' section.")
            return
        
        try:
            ics_data = fetcher.get_ics()
            self.send_response(200)
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="schedule.ics"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", f"public, max-age={fetcher.cache_ttl}")
            self.end_headers()
            self.wfile.write(ics_data.encode("utf-8"))
        except Exception as e:
            logger.error("Error serving quick config: %s", e, exc_info=True)
            self.send_error(500, f"Internal Server Error: {e}")

    def log_message(self, format, *args):
        """Override to use Python logging instead of stderr."""
        logger.info(format, *args)


def cmd_serve(config: Dict[str, Any]):
    """Start the ICS feed server."""
    srv = config.get("server", DEFAULT_CONFIG["server"])
    host = srv.get("host", "0.0.0.0")
    port = srv.get("port", 8080)

    server = HTTPServer((host, port), ICSRequestHandler)
    print(f"\n{'='*60}")
    print(f"  Skola24-to-GCal ICS Feed Server")
    print(f"{'='*60}")
    print(f"  Server:     http://{host}:{port}")
    print(f"{'='*60}")
    print(f"\n  Quick Configs (from config.yaml users: section):")
    users = config.get("users", {})
    for name in users:
        print(f"    /{name}/schedule.ics")
    print(f"\n  URL Parameters:")
    print(f"    host           - Skola24 host domain")
    print(f"    unit_guid      - School unit GUID")
    print(f"    selection      - Class name, teacher ID, etc.")
    print(f"    selection_type - 0=class, 7=teacher, 5=room, 4=personal")
    print(f"\n  Example:")
    print(f"    http://{host}:{port}/marnie/schedule.ics")
    print(f"    http://{host}:{port}/schedule.ics?host=...&unit_guid=...&selection=...")
    print(f"{'='*60}")
    print(f"\n  Health Check:  http://{host}:{port}/health")
    print(f"\n{'='*60}")
    print(f"  Server starting on {host}:{port}...")
    print(f"  Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


def cmd_list_schools(args: argparse.Namespace):
    """List available schools for a host."""
    host = args.host
    print(f"\nFetching schools for {host}...\n")

    units = skola24_api.get_units(host)
    if not units:
        print("No schools found. Check the host domain.")
        return

    print(f"{'School Name':<50} {'Unit GUID'}")
    print("-" * 100)
    for unit in sorted(units, key=lambda u: u.get("unitId", "")):
        name = unit.get("unitId", "Unknown")
        guid = unit.get("unitGuid", "")
        print(f"{name:<50} {guid}")

    print(f"\nTotal: {len(units)} schools")
    print("\nUse the 'unitGuid' value in your config.yaml")


def cmd_list_classes(args: argparse.Namespace):
    """List available classes for a school."""
    host = args.host
    unit_guid = args.unit_guid
    print(f"\nFetching classes for {host} / {unit_guid}...\n")

    classes = skola24_api.list_classes(host, unit_guid)
    if not classes:
        print("No classes found.")
        return

    print(f"{'Class Name':<30} {'Group GUID'}")
    print("-" * 80)
    for cls in sorted(classes, key=lambda c: c.get("groupName", "")):
        name = cls.get("groupName", "Unknown")
        guid = cls.get("groupGuid", "")
        print(f"{name:<30} {guid}")

    print(f"\nTotal: {len(classes)} classes")
    print(
        "\nUse the class name as 'selection' in your config.yaml with selection_type: 0"
    )


def cmd_list_teachers(args: argparse.Namespace):
    """List available teachers for a school."""
    host = args.host
    unit_guid = args.unit_guid
    print(f"\nFetching teachers for {host} / {unit_guid}...\n")

    teachers = skola24_api.list_teachers(host, unit_guid)
    if not teachers:
        print("No teachers found.")
        return

    print(f"{'ID':<10} {'Full Name':<40} {'Person GUID'}")
    print("-" * 100)
    for t in sorted(teachers, key=lambda t: t.get("id", "")):
        tid = t.get("id", "?")
        name = t.get("fullName", "")
        guid = t.get("personGuid", "")
        print(f"{tid:<10} {name:<40} {guid}")

    print(f"\nTotal: {len(teachers)} teachers")
    print(
        "\nUse the teacher ID as 'selection' in your config.yaml with selection_type: 7"
    )


def cmd_list_rooms(args: argparse.Namespace):
    """List available rooms for a school."""
    host = args.host
    unit_guid = args.unit_guid
    print(f"\nFetching rooms for {host} / {unit_guid}...\n")

    rooms = skola24_api.list_rooms(host, unit_guid)
    if not rooms:
        print("No rooms found.")
        return

    print(f"{'Room Name':<30} {'Room EID'}")
    print("-" * 80)
    for r in sorted(rooms, key=lambda r: r.get("name", "")):
        name = r.get("name", "Unknown")
        eid = r.get("eid", "")
        print(f"{name:<30} {eid}")

    print(f"\nTotal: {len(rooms)} rooms")
    print(
        "\nUse the room name as 'selection' in your config.yaml with selection_type: 5"
    )


def cmd_list_groups(args: argparse.Namespace):
    """List available groups for a school."""
    host = args.host
    unit_guid = args.unit_guid
    print(f"\nFetching groups for {host} / {unit_guid}...\n")

    groups = skola24_api.list_groups(host, unit_guid)
    if not groups:
        print("No groups found.")
        return

    print(f"{'Group Name':<30} {'Group GUID'}")
    print("-" * 80)
    for g in sorted(groups, key=lambda g: g.get("groupName", "")):
        name = g.get("groupName", "Unknown")
        guid = g.get("groupGuid", "")
        print(f"{name:<30} {guid}")

    print(f"\nTotal: {len(groups)} groups")


def cmd_init_config(args: argparse.Namespace):
    """Generate an example configuration file."""
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.yaml"
    )

    if os.path.exists(config_path) and not args.force:
        print(f"Config file already exists: {config_path}")
        print("Use --force to overwrite.")
        sys.exit(1)

    with open(config_path, "w") as f:
        f.write(generate_example_config())

    print(f"Example config written to: {config_path}")
    print("Edit it with your school details, then run 'python3 server.py serve'")


def cmd_test_fetch(config: Dict[str, Any]):
    """Test fetching the schedule and print results."""
    errors = validate_config(config)
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    sk = config["skola24"]
    sched = config["schedule"]

    fetcher = ScheduleFetcher(
        host=sk["host"],
        unit_guid=sk["unit_guid"],
        selection_name=sk["selection"],
        selection_type=sk["selection_type"],
        weeks_ahead=sched["weeks_ahead"],
        weeks_behind=sched["weeks_behind"],
        cache_ttl=sched["cache_ttl"],
        calendar_name=sched.get("calendar_name", ""),
    )

    print(f"\nFetching schedule for {sk['selection']} ({sk['host']})...\n")
    try:
        lessons_by_week = fetcher.fetch_schedule()
        total_lessons = sum(len(lessons) for lessons in lessons_by_week.values())
        print(f"Successfully fetched {total_lessons} lessons.")
        for (year, week), lessons in lessons_by_week.items():
            print(f"  Week {week}/{year}: {len(lessons)} lessons")

        ics_data = fetcher.get_ics()
        print(f"\nGenerated ICS data (first 500 chars):\n{ics_data[:500]}...")

    except Exception as e:
        logger.error("Failed to fetch schedule: %s", e, exc_info=True)
        print(f"\nError fetching schedule: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Skola24-to-GCal: Sync Skola24 schedules to Google Calendar."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to configuration YAML file (default: config.yaml)",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Set logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start the ICS feed server")

    # List schools command
    list_schools_parser = subparsers.add_parser(
        "list-schools", help="List available schools for a host"
    )
    list_schools_parser.add_argument(
        "--host",
        required=True,
        help="Skola24 host domain (e.g., it-gymnasiet.skola24.se)",
    )

    # List classes command
    list_classes_parser = subparsers.add_parser(
        "list-classes", help="List available classes for a school unit"
    )
    list_classes_parser.add_argument(
        "--host", required=True, help="Skola24 host domain"
    )
    list_classes_parser.add_argument(
        "--unit-guid", required=True, help="School unit GUID"
    )

    # List teachers command
    list_teachers_parser = subparsers.add_parser(
        "list-teachers", help="List available teachers for a school unit"
    )
    list_teachers_parser.add_argument(
        "--host", required=True, help="Skola24 host domain"
    )
    list_teachers_parser.add_argument(
        "--unit-guid", required=True, help="School unit GUID"
    )

    # List rooms command
    list_rooms_parser = subparsers.add_parser(
        "list-rooms", help="List available rooms for a school unit"
    )
    list_rooms_parser.add_argument("--host", required=True, help="Skola24 host domain")
    list_rooms_parser.add_argument(
        "--unit-guid", required=True, help="School unit GUID"
    )

    # List groups command
    list_groups_parser = subparsers.add_parser(
        "list-groups", help="List available groups for a school unit"
    )
    list_groups_parser.add_argument("--host", required=True, help="Skola24 host domain")
    list_groups_parser.add_argument(
        "--unit-guid", required=True, help="School unit GUID"
    )

    # Init config command
    init_config_parser = subparsers.add_parser(
        "init-config", help="Generate an example config.yaml file"
    )
    init_config_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing config.yaml"
    )

    # Test fetch command
    test_fetch_parser = subparsers.add_parser(
        "test-fetch", help="Fetch and print schedule (for testing)"
    )

    # Test fetch URL command
    test_url_parser = subparsers.add_parser(
        "test-url", help="Test fetching with URL parameters"
    )
    test_url_parser.add_argument("--host", required=True, help="Skola24 host domain")
    test_url_parser.add_argument("--unit-guid", required=True, help="School unit GUID")
    test_url_parser.add_argument("--selection", required=True, help="Class name, teacher ID, etc.")
    test_url_parser.add_argument("--selection-type", type=int, default=0, help="Selection type (0=class, 7=teacher, 5=room, 4=personal)")
    test_url_parser.add_argument("--user", help="User identifier (for caching)")

    args = parser.parse_args()

    # Configure logging
    log_level = args.log_level or os.environ.get("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = load_config(args.config)

    if args.command == "serve":
        cmd_serve(config)
    elif args.command == "list-schools":
        cmd_list_schools(args)
    elif args.command == "list-classes":
        cmd_list_classes(args)
    elif args.command == "list-teachers":
        cmd_list_teachers(args)
    elif args.command == "list-rooms":
        cmd_list_rooms(args)
    elif args.command == "list-groups":
        cmd_list_groups(args)
    elif args.command == "init-config":
        cmd_init_config(args)
    elif args.command == "test-fetch":
        cmd_test_fetch(config)
    elif args.command == "test-url":
        cmd_test_url(args)


def cmd_test_url(args: argparse.Namespace):
    """Test fetching with URL-like parameters."""
    query = {
        "host": [args.host],
        "unit_guid": [args.unit_guid],
        "selection": [args.selection],
    }
    if args.selection_type:
        query["selection_type"] = [str(args.selection_type)]
    if args.user:
        query["user"] = [args.user]

    fetcher = None
    for key, f in fetcher_cache.items():
        test_config = {
            "skola24": {
                "host": f.host,
                "unit_guid": f.unit_guid,
                "selection": f.selection_name,
                "selection_type": f.selection_type,
            },
            "schedule": {
                "weeks_ahead": f.weeks_ahead,
                "weeks_behind": f.weeks_behind,
                "cache_ttl": f.cache_ttl,
            },
        }
        if test_config["skola24"] == {
            "host": args.host,
            "unit_guid": args.unit_guid,
            "selection": args.selection,
            "selection_type": args.selection_type if args.selection_type is not None else 0,
        }:
            fetcher = f
            break

    if not fetcher:
        config = config_from_url_params(query)
        fetcher = ScheduleFetcher(
            host=config["skola24"]["host"],
            unit_guid=config["skola24"]["unit_guid"],
            selection_name=config["skola24"]["selection"],
            selection_type=config["skola24"]["selection_type"],
            weeks_ahead=config["schedule"]["weeks_ahead"],
            weeks_behind=config["schedule"]["weeks_behind"],
            cache_ttl=config["schedule"]["cache_ttl"],
        )

    print(f"\nFetching schedule for {args.selection} ({args.host})...\n")
    try:
        lessons_by_week = fetcher.fetch_schedule()
        total_lessons = sum(len(lessons) for lessons in lessons_by_week.values())
        print(f"Successfully fetched {total_lessons} lessons.")
        for (year, week), lessons in lessons_by_week.items():
            print(f"  Week {week}/{year}: {len(lessons)} lessons")

        ics_data = fetcher.get_ics()
        print(f"\nGenerated ICS data (first 500 chars):\n{ics_data[:500]}...")

    except Exception as e:
        logger.error("Failed to fetch schedule: %s", e, exc_info=True)
        print(f"\nError fetching schedule: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
