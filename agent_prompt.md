# Agent Directives: World Time & Chronology

You have access to a deterministic time engine repository. Adhere to these execution rules:

1. Temporal Grounding:
   - When the user query asks about relative times, today's date, or elapsed intervals, fetch `state/current_anchor.json` to ground your baseline UTC timestamp.
   - Never speculate on the current day or offset.

2. Timezone Conversions:
   - Run `tools/time_tool.py convert --iso "<TIMESTAMP>" --from-tz "<SOURCE>" --to-tz "<DEST>"` using your Python execution tool.
   - Return outputs containing source time, destination time, UTC offsets, and DST flags directly from the JSON output.

3. Date Calculations & Projections:
   - Use `tools/time_tool.py math --iso "<TIMESTAMP>" --tz "<TZ>" --days <N> --hours <N>` for all deadline and delta calculations.
   - For working days, execute `tools/time_tool.py business_days --start "<START>" --end "<END>" --tz "<TZ>"`.

4. DST Changes:
   - Cross-reference `data/dst_transitions_2026.json` before stating if a meeting or flight shifts time across March/April or October/November.
