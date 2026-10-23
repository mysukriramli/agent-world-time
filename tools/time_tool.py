#!/usr/bin/env python3
"""
Agentic Time Calculator
Deterministic world time operations and ISO-8601 duration arithmetic.
Standard Library only: zoneinfo, datetime, json, argparse, sys.
"""

import argparse
from datetime import datetime, timedelta
import json
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

def get_zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        # Fallback aliases
        aliases = {"EST": "America/New_York", "PST": "America/Los_Angeles", "CST": "America/Chicago", "UTC": "UTC", "GMT": "UTC"}
        target = aliases.get(tz_name.upper())
        if target:
            return ZoneInfo(target)
        raise ValueError(f"Invalid IANA timezone: {tz_name}")

def convert_time(dt_str: str, from_tz: str, to_tz: str) -> dict:
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
            "utc_offset_seconds": int(dt.utcoffset().total_seconds())
        },
        "target": {
            "datetime": converted.isoformat(),
            "timezone": str(to_zone),
            "utc_offset_seconds": int(converted.utcoffset().total_seconds()),
            "is_dst": bool(converted.dst() and converted.dst() != timedelta(0))
        },
        "unix_timestamp": int(converted.timestamp())
    }

def calculate_offset(base_dt_str: str, base_tz: str, days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0) -> dict:
    zone = get_zone(base_tz)
    dt = datetime.fromisoformat(base_dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)
    delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    result = dt + delta
    return {
        "original_datetime": dt.isoformat(),
        "applied_delta": {"days": days, "hours": hours, "minutes": minutes, "seconds": seconds},
        "result_datetime": result.isoformat(),
        "timezone": str(zone),
        "unix_timestamp": int(result.timestamp())
    }

def calculate_business_days(start_date_str: str, end_date_str: str, tz: str) -> dict:
    zone = get_zone(tz)
    start_dt = datetime.fromisoformat(start_date_str).replace(tzinfo=zone)
    end_dt = datetime.fromisoformat(end_date_str).replace(tzinfo=zone)
    
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
        "total_days": business_days + weekend_days
    }

def main():
    parser = argparse.ArgumentParser(description="Deterministic Time Operations for LLM Agents")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Convert Command
    conv_p = subparsers.add_parser("convert")
    conv_p.add_argument("--iso", required=True, help="ISO-8601 string (e.g., 2026-10-23T14:00:00)")
    conv_p.add_argument("--from-tz", required=True, help="IANA source timezone")
    conv_p.add_argument("--to-tz", required=True, help="IANA target timezone")

    # Math Delta Command
    math_p = subparsers.add_parser("math")
    math_p.add_argument("--iso", required=True, help="Base ISO-8601 timestamp")
    math_p.add_argument("--tz", default="UTC", help="IANA timezone")
    math_p.add_argument("--days", type=int, default=0)
    math_p.add_argument("--hours", type=int, default=0)
    math_p.add_argument("--minutes", type=int, default=0)
    math_p.add_argument("--seconds", type=int, default=0)

    # Business Days Command
    bday_p = subparsers.add_parser("business_days")
    bday_p.add_argument("--start", required=True, help="Start ISO-8601 date")
    bday_p.add_argument("--end", required=True, help="End ISO-8601 date")
    bday_p.add_argument("--tz", default="UTC", help="IANA timezone")

    args = parser.parse_args()

    try:
        if args.command == "convert":
            payload = convert_time(args.iso, args.from_tz, args.to_tz)
        elif args.command == "math":
            payload = calculate_offset(args.iso, args.tz, args.days, args.hours, args.minutes, args.seconds)
        elif args.command == "business_days":
            payload = calculate_business_days(args.start, args.end, args.tz)
        else:
            payload = {"error": "Unsupported command"}
        print(json.dumps(payload, indent=2))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
