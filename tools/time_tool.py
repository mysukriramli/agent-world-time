#!/usr/bin/env python3
"""
tools/time_tool.py - Deterministic Time Engine for LLM Agents
Features: Timezone conversion, date math, business day counters, 
multi-zone meeting window overlap optimizer, and --compact token minimization.

Dependencies: Standard Library only (Python 3.9+).
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_zone(tz_name: str) -> ZoneInfo:
    """Resolve IANA timezone strings with common alias fallbacks."""
    aliases = {
        "EST": "America/New_York",
        "EDT": "America/New_York",
        "PST": "America/Los_Angeles",
        "PDT": "America/Los_Angeles",
        "CST": "America/Chicago",
        "CDT": "America/Chicago",
        "MST": "America/Denver",
        "MDT": "America/Denver",
        "UTC": "UTC",
        "GMT": "UTC",
        "BST": "Europe/London",
        "CET": "Europe/Paris",
        "CEST": "Europe/Paris",
        "JST": "Asia/Tokyo",
        "AEST": "Australia/Sydney",
        "AEDT": "Australia/Sydney",
        "SGT": "Asia/Singapore",
        "IST": "Asia/Kolkata",
    }
    cleaned = tz_name.strip()
    try:
        return ZoneInfo(cleaned)
    except ZoneInfoNotFoundError:
        target = aliases.get(cleaned.upper())
        if target:
            return ZoneInfo(target)
        raise ValueError(f"Invalid or unrecognized IANA timezone: '{tz_name}'")


def parse_time_to_minutes(time_str: str) -> int:
    """Convert 'HH:MM' or 'HH' string into minutes from midnight."""
    parts = time_str.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    if not (0 <= hour <= 24 and 0 <= minute < 60):
        raise ValueError(f"Invalid time format: {time_str}")
    return hour * 60 + minute


def minutes_to_str(minutes: int) -> str:
    """Convert minutes from midnight back into 'HH:MM' format."""
    normalized = minutes % 1440
    return f"{normalized // 60:02d}:{normalized % 60:02d}"


def convert_time(dt_str: str, from_tz: str, to_tz: str) -> dict:
    """Convert an ISO-8601 timestamp between two timezones."""
    from_zone = get_zone(from_tz)
    to_zone = get_zone(to_tz)
    dt = datetime.fromisoformat(dt_str)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=from_zone)
    else:
        dt = dt.astimezone(from_zone)

    converted = dt.astimezone(to_zone)
    return {
        "source": {
            "datetime": dt.isoformat(),
            "timezone": str(from_zone),
            "utc_offset_seconds": int(dt.utcoffset().total_seconds()),
        },
        "target": {
            "datetime": converted.isoformat(),
            "timezone": str(to_zone),
            "utc_offset_seconds": int(converted.utcoffset().total_seconds()),
            "is_dst": bool(converted.dst() and converted.dst() != timedelta(0)),
        },
        "unix_timestamp": int(converted.timestamp()),
    }


def calculate_offset(
    base_dt_str: str,
    base_tz: str,
    days: int = 0,
    hours: int = 0,
    minutes: int = 0,
    seconds: int = 0,
) -> dict:
    """Add or subtract chronological intervals relative to an ISO timestamp."""
    zone = get_zone(base_tz)
    dt = datetime.fromisoformat(base_dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)
    else:
        dt = dt.astimezone(zone)

    delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    result = dt + delta
    return {
        "original_datetime": dt.isoformat(),
        "applied_delta": {
            "days": days,
            "hours": hours,
            "minutes": minutes,
            "seconds": seconds,
        },
        "result_datetime": result.isoformat(),
        "timezone": str(zone),
        "unix_timestamp": int(result.timestamp()),
    }


def calculate_business_days(start_date_str: str, end_date_str: str, tz: str) -> dict:
    """Count business days (Mon-Fri) and weekends between two dates."""
    zone = get_zone(tz)
    start_dt = datetime.fromisoformat(start_date_str)
    end_dt = datetime.fromisoformat(end_date_str)

    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=zone)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=zone)

    current = start_dt
    business_days = 0
    weekend_days = 0
    step = timedelta(days=1) if start_dt <= end_dt else timedelta(days=-1)

    while (current <= end_dt if step.days > 0 else current >= end_dt):
        if current.weekday() < 5:
            business_days += 1
        else:
            weekend_days += 1
        current += step

    return {
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "timezone": str(zone),
        "business_days": business_days,
        "weekend_days": weekend_days,
        "total_days": business_days + weekend_days,
    }


def find_overlap(
    zones_list: list[str],
    date_str: str | None = None,
    work_start_str: str = "09:00",
    work_end_str: str = "17:00",
    step_minutes: int = 60,
) -> dict:
    """
    Evaluates 24-hour UTC slots to find strict multi-zone meeting overlaps 
    or calculate minimal-fatigue compromise slots.
    """
    resolved_zones = [get_zone(z) for z in zones_list]
    work_start = parse_time_to_minutes(work_start_str)
    work_end = parse_time_to_minutes(work_end_str)

    if date_str:
        base_date = datetime.fromisoformat(date_str).date()
    else:
        base_date = datetime.now(timezone.utc).date()

    strict_overlaps = []
    compromise_candidates = []

    # Step through candidate slots across the 24-hour UTC day
    total_steps = 1440 // step_minutes
    for i in range(total_steps):
        current_minute = i * step_minutes
        slot_utc = datetime(
            base_date.year,
            base_date.month,
            base_date.day,
            current_minute // 60,
            current_minute % 60,
            tzinfo=timezone.utc,
        )

        slot_times = {}
        penalty_score = 0
        all_working = True

        for zone in resolved_zones:
            local_dt = slot_utc.astimezone(zone)
            local_min = local_dt.hour * 60 + local_dt.minute
            local_time_formatted = local_dt.strftime("%H:%M")

            # Status and fatigue evaluation
            if work_start <= local_min <= work_end:
                status = "working"
            elif (work_start - 120) <= local_min < work_start:
                status = "early"
                penalty_score += 1
                all_working = False
            elif work_end < local_min <= (work_end + 180):
                status = "late"
                penalty_score += 1
                all_working = False
            else:
                status = "night"
                penalty_score += 4
                all_working = False

            slot_times[str(zone)] = f"{local_time_formatted} ({status})"

        slot_record = {
            "utc": slot_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "local_times": slot_times,
            "penalty_score": penalty_score,
        }

        if all_working:
            strict_overlaps.append(slot_record)
        else:
            compromise_candidates.append(slot_record)

    # Sort compromise candidates by lowest penalty score
    compromise_candidates.sort(key=lambda x: x["penalty_score"])

    return {
        "date": base_date.isoformat(),
        "work_window": f"{work_start_str} - {work_end_str}",
        "zones_evaluated": [str(z) for z in resolved_zones],
        "strict_overlap_count": len(strict_overlaps),
        "strict_overlaps": strict_overlaps,
        "best_compromise_windows": compromise_candidates[:3] if not strict_overlaps else [],
    }


def to_compact(command: str, payload: dict) -> dict:
    """Strips verbose keys into abbreviated, token-dense structures for LLM contexts."""
    if command == "convert":
        return {
            "src": payload["source"]["datetime"],
            "src_tz": payload["source"]["timezone"],
            "tgt": payload["target"]["datetime"],
            "tgt_tz": payload["target"]["timezone"],
            "dst": 1 if payload["target"]["is_dst"] else 0,
            "epoch": payload["unix_timestamp"],
        }
    elif command == "math":
        return {
            "orig": payload["original_datetime"],
            "res": payload["result_datetime"],
            "tz": payload["timezone"],
            "epoch": payload["unix_timestamp"],
        }
    elif command == "business_days":
        return {
            "start": payload["start"],
            "end": payload["end"],
            "b_days": payload["business_days"],
            "w_days": payload["weekend_days"],
            "tot": payload["total_days"],
        }
    elif command == "find_overlap":
        compact_strict = [
            {"utc": item["utc"], "slots": item["local_times"]}
            for item in payload.get("strict_overlaps", [])
        ]
        compact_alt = [
            {"utc": item["utc"], "score": item["penalty_score"], "slots": item["local_times"]}
            for item in payload.get("best_compromise_windows", [])
        ]
        return {
            "date": payload["date"],
            "strict": compact_strict,
            "alt": compact_alt,
        }
    return payload


def main():
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit token-minimized, single-line JSON without redundant schema metadata",
    )

    parser = argparse.ArgumentParser(
        description="Deterministic Time Engine for AI Agents",
        parents=[common_parser],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: convert
    conv_p = subparsers.add_parser("convert", parents=[common_parser])
    conv_p.add_argument("--iso", required=True, help="ISO-8601 string (e.g. 2026-10-23T14:00:00)")
    conv_p.add_argument("--from-tz", required=True, help="Source IANA timezone or alias")
    conv_p.add_argument("--to-tz", required=True, help="Target IANA timezone or alias")

    # Subcommand: math
    math_p = subparsers.add_parser("math", parents=[common_parser])
    math_p.add_argument("--iso", required=True, help="Base ISO-8601 timestamp")
    math_p.add_argument("--tz", default="UTC", help="Base timezone (default: UTC)")
    math_p.add_argument("--days", type=int, default=0)
    math_p.add_argument("--hours", type=int, default=0)
    math_p.add_argument("--minutes", type=int, default=0)
    math_p.add_argument("--seconds", type=int, default=0)

    # Subcommand: business_days
    bday_p = subparsers.add_parser("business_days", parents=[common_parser])
    bday_p.add_argument("--start", required=True, help="Start ISO-8601 date")
    bday_p.add_argument("--end", required=True, help="End ISO-8601 date")
    bday_p.add_argument("--tz", default="UTC", help="IANA timezone")

    # Subcommand: find_overlap
    overlap_p = subparsers.add_parser("find_overlap", parents=[common_parser])
    overlap_p.add_argument(
        "--zones",
        required=True,
        help="Comma-separated IANA zones (e.g. 'America/Los_Angeles,Europe/London,Asia/Tokyo')",
    )
    overlap_p.add_argument("--date", default=None, help="Target date YYYY-MM-DD (defaults to today UTC)")
    overlap_p.add_argument("--work-start", default="09:00", help="Start of workday (default: 09:00)")
    overlap_p.add_argument("--work-end", default="17:00", help="End of workday (default: 17:00)")
    overlap_p.add_argument("--step-minutes", type=int, default=60, help="Search resolution in minutes")

    args = parser.parse_args()

    try:
        if args.command == "convert":
            payload = convert_time(args.iso, args.from_tz, args.to_tz)
        elif args.command == "math":
            payload = calculate_offset(
                args.iso, args.tz, args.days, args.hours, args.minutes, args.seconds
            )
        elif args.command == "business_days":
            payload = calculate_business_days(args.start, args.end, args.tz)
        elif args.command == "find_overlap":
            zones = [z.strip() for z in args.zones.split(",") if z.strip()]
            payload = find_overlap(
                zones_list=zones,
                date_str=args.date,
                work_start_str=args.work_start,
                work_end_str=args.work_end,
                step_minutes=args.step_minutes,
            )
        else:
            payload = {"error": "Unsupported command"}

        if args.compact:
            compact_data = to_compact(args.command, payload)
            print(json.dumps(compact_data, separators=(",", ":")))
        else:
            print(json.dumps(payload, indent=2))

    except Exception as exc:
        err_payload = {"error": str(exc)}
        if getattr(args, "compact", False):
            print(json.dumps(err_payload, separators=(",", ":")), file=sys.stderr)
        else:
            print(json.dumps(err_payload, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
