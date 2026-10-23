#!/usr/bin/env python3
"""
tools/time_tool.py - Complete Deterministic Time Engine for LLM Agents

Features:
- Timezone conversion with PEP 495 fold handling & spring-forward gap auto-adjustment.
- City name, code, and alias resolution (e.g., 'nyc', 'sf', 'tokyo') to canonical IANA zones.
- Date interval and duration arithmetic (math).
- Business day and weekend calculation.
- Multi-zone meeting overlap optimizer with fatigue penalties.
- Cron recurring schedule evaluator (next N occurrences across DST).
- Deterministic simulation override via --mock-now.
- Context-window token minimization via --compact.

Standard Library only: zoneinfo, datetime, json, argparse, sys, os.
Compatible with Python 3.9+.
"""

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Embedded fallback map for cities, common slugs, and abbreviations
STATIC_CITY_TZ_MAP = {
    # US & Canada
    "nyc": "America/New_York",
    "new york": "America/New_York",
    "sf": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles",
    "chicago": "America/Chicago",
    "denver": "America/Denver",
    "toronto": "America/Toronto",
    "vancouver": "America/Vancouver",
    "seattle": "America/Los_Angeles",
    "austin": "America/Chicago",
    "boston": "America/New_York",
    # Europe
    "london": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "amsterdam": "Europe/Amsterdam",
    "madrid": "Europe/Madrid",
    "rome": "Europe/Rome",
    "zurich": "Europe/Zurich",
    "dublin": "Europe/Dublin",
    # Asia & Middle East
    "tokyo": "Asia/Tokyo",
    "singapore": "Asia/Singapore",
    "hong kong": "Asia/Hong_Kong",
    "seoul": "Asia/Seoul",
    "shanghai": "Asia/Shanghai",
    "beijing": "Asia/Shanghai",
    "dubai": "Asia/Dubai",
    "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "bangkok": "Asia/Bangkok",
    # Oceania & South America
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "auckland": "Pacific/Auckland",
    "sao paulo": "America/Sao_Paulo",
    "buenos aires": "America/Argentina/Buenos_Aires",
    # Common Timezone Abbreviations
    "utc": "UTC",
    "gmt": "UTC",
    "est": "America/New_York",
    "edt": "America/New_York",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "bst": "Europe/London",
    "cet": "Europe/Paris",
    "cest": "Europe/Paris",
    "jst": "Asia/Tokyo",
    "ist": "Asia/Kolkata",
    "sgt": "Asia/Singapore",
    "aest": "Australia/Sydney",
    "aedt": "Australia/Sydney",
}


def get_zone(tz_identifier: str) -> ZoneInfo:
    """Resolve IANA timezone strings, external JSON maps, and static alias fallbacks."""
    cleaned = tz_identifier.strip()
    lookup_key = cleaned.lower()

    # 1. Attempt to resolve from data/city_tz_map.json if present
    data_map_path = os.path.join(os.path.dirname(__file__), "..", "data", "city_tz_map.json")
    if os.path.isfile(data_map_path):
        try:
            with open(data_map_path, "r", encoding="utf-8") as f:
                disk_map = json.load(f)
                if lookup_key in disk_map:
                    return ZoneInfo(disk_map[lookup_key])
        except Exception:
            pass

    # 2. Check built-in fallback dictionary
    if lookup_key in STATIC_CITY_TZ_MAP:
        return ZoneInfo(STATIC_CITY_TZ_MAP[lookup_key])

    # 3. Direct IANA lookup
    try:
        return ZoneInfo(cleaned)
    except ZoneInfoNotFoundError:
        raise ValueError(
            f"Unable to resolve timezone: '{tz_identifier}'. "
            "Please provide a valid IANA identifier (e.g., 'America/New_York', 'UTC')."
        )


def get_simulated_now(tz: ZoneInfo, mock_now_str: str | None = None) -> datetime:
    """Return simulated UTC-anchored datetime if mock-now is provided, else actual now."""
    if mock_now_str:
        dt = datetime.fromisoformat(mock_now_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz)
    return datetime.now(tz)


def parse_time_to_minutes(time_str: str) -> int:
    """Convert 'HH:MM' string into integer minutes since midnight."""
    parts = time_str.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    if not (0 <= hour <= 24 and 0 <= minute < 60):
        raise ValueError(f"Invalid time format: {time_str}")
    return hour * 60 + minute


def convert_time(dt_str: str, from_tz: str, to_tz: str, fold: int = 0) -> dict:
    """
    Converts an ISO-8601 timestamp between timezones with PEP 495 fold handling
    and non-existent spring-forward transition detection.
    """
    from_zone = get_zone(from_tz)
    to_zone = get_zone(to_tz)
    dt = datetime.fromisoformat(dt_str)

    gap_adjusted = False
    adjustment_note = None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=from_zone, fold=fold)
        # Verify if timestamp falls into a DST spring-forward skip gap
        test_utc = dt.astimezone(timezone.utc)
        roundtrip = test_utc.astimezone(from_zone)
        if roundtrip.hour != dt.hour or roundtrip.minute != dt.minute:
            gap_adjusted = True
            dt = dt + timedelta(hours=1)
            adjustment_note = (
                "Requested wall time fell into a DST spring-forward gap (did not exist). "
                "Automatically adjusted forward by +1 hour."
            )
    else:
        dt = dt.astimezone(from_zone)

    converted = dt.astimezone(to_zone)

    return {
        "source": {
            "datetime": dt.isoformat(),
            "timezone": str(from_zone),
            "utc_offset_seconds": int(dt.utcoffset().total_seconds()),
            "fold_applied": fold,
            "gap_adjusted": gap_adjusted,
            "note": adjustment_note,
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
    """Calculate working days (Mon-Fri) and weekends between two dates."""
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

    while current <= end_dt if step.days > 0 else current >= end_dt:
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
    mock_now_str: str | None = None,
) -> dict:
    """Evaluates 24h UTC intervals to find mutual working-hour windows or minimal penalty slots."""
    resolved_zones = [get_zone(z) for z in zones_list]
    work_start = parse_time_to_minutes(work_start_str)
    work_end = parse_time_to_minutes(work_end_str)

    if date_str:
        base_date = datetime.fromisoformat(date_str).date()
    else:
        base_date = get_simulated_now(timezone.utc, mock_now_str).date()

    strict_overlaps = []
    compromise_candidates = []
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
            local_str = local_dt.strftime("%H:%M")

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

            slot_times[str(zone)] = f"{local_str} ({status})"

        record = {
            "utc": slot_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "local_times": slot_times,
            "penalty_score": penalty_score,
        }

        if all_working:
            strict_overlaps.append(record)
        else:
            compromise_candidates.append(record)

    compromise_candidates.sort(key=lambda x: x["penalty_score"])

    return {
        "date": base_date.isoformat(),
        "work_window": f"{work_start_str} - {work_end_str}",
        "zones_evaluated": [str(z) for z in resolved_zones],
        "strict_overlap_count": len(strict_overlaps),
        "strict_overlaps": strict_overlaps,
        "best_compromise_windows": compromise_candidates[:3] if not strict_overlaps else [],
    }


def cron_field_matches(pattern: str, val: int, is_dow: bool = False) -> bool:
    """Evaluate standard cron syntax for a discrete time component."""
    pattern = pattern.strip()
    if pattern == "*":
        return True
    if pattern.startswith("*/"):
        step = int(pattern.split("/")[1])
        return val % step == 0
    if "," in pattern:
        subparts = [p.strip() for p in pattern.split(",")]
        return any(cron_field_matches(sub, val, is_dow) for sub in subparts)
    if "-" in pattern:
        start, end = map(int, pattern.split("-"))
        return start <= val <= end

    target = int(pattern)
    if is_dow and target == 7:
        target = 0
    return val == target


def cron_next(
    cron_expr: str,
    tz_str: str,
    count: int = 5,
    mock_now_str: str | None = None,
) -> dict:
    """Deterministic forward evaluation of next N timestamps for a 5-part cron pattern."""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError("Invalid cron syntax. Expected 5 fields: 'minute hour day month day_of_week'")

    min_p, hour_p, dom_p, mon_p, dow_p = parts
    zone = get_zone(tz_str)
    current = get_simulated_now(zone, mock_now_str).replace(second=0, microsecond=0) + timedelta(minutes=1)

    occurrences = []
    # Search window bounded to 50,000 forward minutes to prevent infinite loops on unmatchable dates
    iterations = 0
    while len(occurrences) < count and iterations < 50000:
        iterations += 1
        dow = current.weekday()
        cron_dow = 0 if dow == 6 else dow + 1

        if (
            cron_field_matches(min_p, current.minute)
            and cron_field_matches(hour_p, current.hour)
            and cron_field_matches(dom_p, current.day)
            and cron_field_matches(mon_p, current.month)
            and cron_field_matches(dow_p, cron_dow, is_dow=True)
        ):
            occurrences.append(
                {
                    "local": current.isoformat(),
                    "utc": current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "epoch": int(current.timestamp()),
                }
            )
        current += timedelta(minutes=1)

    return {
        "cron_expression": cron_expr,
        "timezone": str(zone),
        "count_requested": count,
        "occurrences": occurrences,
    }


def to_compact(command: str, payload: dict) -> dict:
    """Transform verbose JSON payloads into token-dense formats for agent context windows."""
    if command == "convert":
        return {
            "src": payload["source"]["datetime"],
            "src_tz": payload["source"]["timezone"],
            "tgt": payload["target"]["datetime"],
            "tgt_tz": payload["target"]["timezone"],
            "dst": 1 if payload["target"]["is_dst"] else 0,
            "epoch": payload["unix_timestamp"],
            "gap_adj": 1 if payload["source"].get("gap_adjusted") else 0,
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
    elif command == "cron_next":
        return {
            "cron": payload["cron_expression"],
            "tz": payload["timezone"],
            "next": [item["local"] for item in payload.get("occurrences", [])],
        }
    return payload


def main():
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit token-minimized, single-line JSON without redundant metadata",
    )
    common_parser.add_argument(
        "--mock-now",
        default=None,
        help="Override reference 'now' for deterministic testing (ISO-8601 string)",
    )

    parser = argparse.ArgumentParser(
        description="Comprehensive Deterministic Time Engine for LLM Agents",
        parents=[common_parser],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Convert
    conv_p = subparsers.add_parser("convert", parents=[common_parser])
    conv_p.add_argument("--iso", required=True, help="ISO-8601 timestamp string")
    conv_p.add_argument("--from-tz", required=True, help="Source IANA timezone, city name, or alias")
    conv_p.add_argument("--to-tz", required=True, help="Target IANA timezone, city name, or alias")
    conv_p.add_argument(
        "--fold",
        type=int,
        choices=[0, 1],
        default=0,
        help="PEP 495 fold choice: 0 = earlier standard time, 1 = later daylight time",
    )

    # Math
    math_p = subparsers.add_parser("math", parents=[common_parser])
    math_p.add_argument("--iso", required=True, help="Base ISO-8601 timestamp")
    math_p.add_argument("--tz", default="UTC", help="Base timezone or alias (default: UTC)")
    math_p.add_argument("--days", type=int, default=0)
    math_p.add_argument("--hours", type=int, default=0)
    math_p.add_argument("--minutes", type=int, default=0)
    math_p.add_argument("--seconds", type=int, default=0)

    # Business Days
    bday_p = subparsers.add_parser("business_days", parents=[common_parser])
    bday_p.add_argument("--start", required=True, help="Start ISO-8601 date string")
    bday_p.add_argument("--end", required=True, help="End ISO-8601 date string")
    bday_p.add_argument("--tz", default="UTC", help="Timezone context")

    # Meeting Overlap
    overlap_p = subparsers.add_parser("find_overlap", parents=[common_parser])
    overlap_p.add_argument(
        "--zones",
        required=True,
        help="Comma-separated IANA zones, cities, or aliases (e.g. 'sf,london,tokyo')",
    )
    overlap_p.add_argument("--date", default=None, help="Evaluation date (YYYY-MM-DD)")
    overlap_p.add_argument("--work-start", default="09:00", help="Workday start (HH:MM)")
    overlap_p.add_argument("--work-end", default="17:00", help="Workday end (HH:MM)")
    overlap_p.add_argument("--step-minutes", type=int, default=60, help="Search step resolution")

    # Cron Evaluation
    cron_p = subparsers.add_parser("cron_next", parents=[common_parser])
    cron_p.add_argument("--expr", required=True, help="5-part cron pattern (e.g. '0 9 * * 1')")
    cron_p.add_argument("--tz", required=True, help="Target IANA timezone or city alias")
    cron_p.add_argument("--count", type=int, default=5, help="Number of forward runs to generate")

    args = parser.parse_args()

    try:
        if args.command == "convert":
            payload = convert_time(args.iso, args.from_tz, args.to_tz, fold=args.fold)
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
                mock_now_str=args.mock_now,
            )
        elif args.command == "cron_next":
            payload = cron_next(
                cron_expr=args.expr,
                tz_str=args.tz,
                count=args.count,
                mock_now_str=args.mock_now,
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
