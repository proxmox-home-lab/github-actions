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

def extract_plan_block(text: str, summary_line: str) -> str:
    start_tf = text.find("Terraform will perform the following actions:")
    start_tofu = text.find("OpenTofu will perform the following actions:")
    start = start_tf if start_tf != -1 else start_tofu
    end = text.find(summary_line)
    if start != -1 and end != -1 and end > start:
        return text[start:end].strip()
    return ""

# status lines we want to keep (ordered)
STATUS_PATTERNS = [
    re.compile(r'^Acquiring state lock\. This may take a few moments\.\.\.$'),
    re.compile(r'.*: Refreshing state\.\.\. \[id=.*\]$'),
    re.compile(r'.*: Modifying\.\.\. \[id=.*\]$'),
    re.compile(r'.*: Modifications complete.* \[id=.*\]$'),
    re.compile(r'^Apply complete!\s+Resources:\s+\d+\s+added,\s+\d+\s+changed,\s+\d+\s+destroyed\.$'),
]

def extract_status_lines(entries, max_lines=12) -> str:
    """Pick a small, useful subset of operational lines (lock/refresh/modify/apply)."""
    picked = []
    seen = set()

    for _, msg in entries:
        msg = msg.strip()
        if not msg:
            continue
        for pat in STATUS_PATTERNS:
            if pat.match(msg):
                # de-dup exact lines (helps with repeated refresh/apply blanks)
                if msg not in seen:
                    seen.add(msg)
                    picked.append(msg)
                break
        if len(picked) >= max_lines:
            break

    return "\n".join(picked).strip()

# Parse per-unit entries
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
    status = extract_status_lines(entries)

    # Primary summary
    if "No changes. Your infrastructure matches the configuration." in text:
        # If apply run, you might still have "Apply complete! 0 changed" etc.
        m_apply = apply_rx.search(text)
        if m_apply:
            return ("✅", m_apply.group(1), "", status, warn_err)
        return ("✅", "No changes", "", status, warn_err)

    m_plan = plan_rx.search(text)
    if m_plan:
        summary = m_plan.group(1)
        plan_block = extract_plan_block(text, summary)
        return ("✏️", summary, plan_block, status, warn_err)

    m_apply = apply_rx.search(text)
    if m_apply:
        summary = m_apply.group(1)
        # Plan block sometimes appears in apply logs as well (like in your sample)
        plan_block = extract_plan_block(text, summary)
        return ("🚀", summary, plan_block, status, warn_err)

    if warn_err:
        first = warn_err.splitlines()[0][:200]
        return ("⚠️", first, "", status, warn_err)

    return ("⚠️", "No summary found", "", status, warn_err)

# Build Markdown
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
        icon, summary, plan_block, status, warn_err = summarize_unit(units[unit])
        per_unit[short] = (icon, summary, plan_block, status, warn_err)
        lines.append(f"| `{short}` | {icon} | {summary} |")

    lines.append("")

    # Details blocks
    for short, (icon, summary, plan_block, status, warn_err) in per_unit.items():
        if not plan_block and not warn_err and not status:
            continue

        lines.append(f"<details><summary><b>{icon} {short}</b></summary>\n")

        if status:
            lines.append("#### Status")
            lines.append("```text")
            lines.append(clip(status, 3000).rstrip())
            lines.append("```\n")

        if warn_err:
            lines.append("#### Warnings/Errors")
            lines.append("```text")
            lines.append(clip(warn_err, 4000).rstrip())
            lines.append("```\n")

        if plan_block:
            lines.append("#### Plan / Changes")
            lines.append("```diff")
            lines.append(clip(plan_block, 12000).rstrip())
            lines.append("```\n")

        lines.append("</details>\n")

out = "\n".join(lines).rstrip() + "\n"
out = clip(out, limit)

print("summary<<EOF")
print(out)
print("EOF")