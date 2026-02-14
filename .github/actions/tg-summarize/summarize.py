#!/usr/bin/env python3
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
limit = int(sys.argv[2])

ansi = re.compile(r'\x1b\[[0-9;]*m')

# Accept optional timestamp prefix + terraform/tofu tool prefix
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
    # Terraform vs OpenTofu header
    start_tf = text.find("Terraform will perform the following actions:")
    start_tofu = text.find("OpenTofu will perform the following actions:")
    start = start_tf if start_tf != -1 else start_tofu
    end = text.find(summary_line)
    if start != -1 and end != -1 and end > start:
        return text[start:end].strip()
    return ""

# Collect per-unit lines
units = {}
for ln in log_path.read_text(errors="ignore").splitlines():
    ln = ansi.sub('', ln)  # ✅ strip ANSI from the whole line first
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
        return "✅", "No changes", "", warn_err

    m = plan_rx.search(text)
    if m:
        summary = m.group(1)
        details = extract_details(text, summary)
        return "✏️", summary, details, warn_err

    m = apply_rx.search(text)
    if m:
        summary = m.group(1)
        # details may or may not exist in filtered output; try anyway
        details = extract_details(text, summary)
        return "🚀", summary, details, warn_err

    if warn_err:
        first = warn_err.splitlines()[0][:200]
        return "⚠️", first, "", warn_err

    return "⚠️", "No summary found", "", ""

lines = ["## Terragrunt summary\n"]

if not units:
    lines.append("> No STDOUT/WARN/ERROR terraform/tofu lines detected.")
else:
    for unit in sorted(units.keys()):
        short = unit.split("/")[-1]
        icon, summary, details, warn_err = summarize_unit(units[unit])

        lines.append(f"- {icon} **{short}** — {summary}")

        if warn_err:
            lines.append("")
            lines.append("  <details><summary>Warnings/Errors</summary>")
            lines.append("")
            lines.append("  ```text")
            for l in clip(warn_err, 2000).splitlines():
                lines.append(f"  {l}")
            lines.append("  ```")
            lines.append("")
            lines.append("  </details>")

        if details:
            lines.append("")
            lines.append("  <details><summary>Details</summary>")
            lines.append("")
            lines.append("  ```diff")
            for l in clip(details, 5000).splitlines():
                lines.append(f"  {l}")
            lines.append("  ```")
            lines.append("")
            lines.append("  </details>")

        lines.append("")

out = "\n".join(lines).rstrip() + "\n"
out = clip(out, limit)

print("summary<<EOF")
print(out)
print("EOF")