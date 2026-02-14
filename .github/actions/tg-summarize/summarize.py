#!/usr/bin/env python3
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
limit = int(sys.argv[2])

ansi = re.compile(r'\x1b\[[0-9;]*m')

rx = re.compile(
    r'^(?:\d{2}:\d{2}:\d{2}\.\d+\s+)?'
    r'(STDOUT|WARN|ERROR)\s+\[(?P<unit>[^\]]+)\]\s+(?:terraform|tofu):\s?(?P<msg>.*)$'
)

plan_rx = re.compile(r'(Plan:\s+\d+\s+to add,\s+\d+\s+to change,\s+\d+\s+to destroy\.)')
apply_rx = re.compile(r'(Apply complete!\s+Resources:\s+\d+\s+added,\s+\d+\s+changed,\s+\d+\s+destroyed\.)')

def clip(s: str, n: int) -> str:
    if not s:
        return ""
    if len(s) <= n:
        return s
    return s[: max(0, n - 13)] + "\n[TRUNCATED]\n"

def extract_warn_err(entries) -> str:
    we = [msg for lvl, msg in entries if lvl in ("WARN", "ERROR") and msg.strip()]
    return "\n".join(we).strip()

def extract_details(text: str, summary_line: str) -> str:
    start_tf = text.find("Terraform will perform the following actions:")
    start_tofu = text.find("OpenTofu will perform the following actions:")
    start = start_tf if start_tf != -1 else start_tofu
    end = text.find(summary_line)
    if start != -1 and end != -1 and end > start:
        return text[start:end].strip()
    return ""

# Parse per-unit
units = {}
for ln in log_path.read_text(errors="ignore").splitlines():
    ln = ansi.sub('', ln)
    m = rx.match(ln)
    if not m:
        continue
    unit = m.group("unit")
    lvl = m.group(1)
    msg = m.group("msg")
    units.setdefault(unit, []).append((lvl, msg))

def summarize_unit(entries):
    text = "\n".join(msg for _, msg in entries)
    warn_err = extract_warn_err(entries)

    if "No changes. Your infrastructure matches the configuration." in text:
        return ("✅", "No changes", "", warn_err)

    m = plan_rx.search(text)
    if m:
        summary = m.group(1)
        details = extract_details(text, summary)
        return ("✏️", summary, details, warn_err)

    m = apply_rx.search(text)
    if m:
        summary = m.group(1)
        details = extract_details(text, summary)  # may be empty
        return ("🚀", summary, details, warn_err)

    if warn_err:
        first = warn_err.splitlines()[0][:200]
        return ("⚠️", first, "", warn_err)

    return ("⚠️", "No summary found", "", "")

# Build markdown
lines = []
lines.append("## Terragrunt summary\n")

if not units:
    lines.append("> No STDOUT/WARN/ERROR terraform/tofu lines detected.\n")
else:
    # Summary table
    lines.append("| Unit | Result | |")
    lines.append("|---|---:|---|")

    per_unit = {}
    for unit in sorted(units.keys()):
        short = unit.split("/")[-1]
        icon, summary, details, warn_err = summarize_unit(units[unit])
        per_unit[short] = (icon, summary, details, warn_err)
        lines.append(f"| `{short}` | {icon} | {summary} |")

    lines.append("")

    # Details blocks
    for short, (icon, summary, details, warn_err) in per_unit.items():
        if not details and not warn_err:
            continue

        lines.append(f"<details><summary><b>{icon} {short}</b></summary>\n")

        if warn_err:
            lines.append("#### Warnings/Errors")
            lines.append("```text")
            lines.append(clip(warn_err, 4000).rstrip())
            lines.append("```\n")

        if details:
            lines.append("#### Details")
            lines.append("```diff")
            lines.append(clip(details, 12000).rstrip())
            lines.append("```\n")

        lines.append("</details>\n")

out = "\n".join(lines).rstrip() + "\n"
out = clip(out, limit)

print("summary<<EOF")
print(out)
print("EOF")