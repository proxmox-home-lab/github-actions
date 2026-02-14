#!/usr/bin/env python3
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
mode = sys.argv[2].strip().lower()
step_url = sys.argv[3].strip()
run_outcome = sys.argv[4].strip().lower()
limit = int(sys.argv[5])

if mode not in ("plan", "apply"):
    mode = "plan"

MODE_ICON = {"plan": "📋", "apply": "🚀"}
mode_icon = MODE_ICON[mode]
mode_label = mode.upper()

ansi = re.compile(r'\x1b\[[0-9;]*m')

# Matches:
# 15:45:34.412 STDOUT [unit] tofu: message
# 15:45:34.412 WARN   [unit] terraform: message
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

STATUS_PATTERNS = [
    re.compile(r'^Acquiring state lock\. This may take a few moments\.\.\.$'),
    re.compile(r'.*: Refreshing state\.\.\. \[id=.*\]$'),
    re.compile(r'.*: Modifying\.\.\. \[id=.*\]$'),
    re.compile(r'.*: Modifications complete.* \[id=.*\]$'),
    re.compile(r'^Apply complete!\s+Resources:\s+\d+\s+added,\s+\d+\s+changed,\s+\d+\s+destroyed\.$'),
]

def extract_status_lines(entries, max_lines=18) -> str:
    picked = []
    seen = set()
    for _, msg in entries:
        msg = msg.strip()
        if not msg:
            continue
        for pat in STATUS_PATTERNS:
            if pat.match(msg):
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
    ln = ansi.sub('', ln)  # ✅ strip ANSI from full line first
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

    if mode == "apply":
        m_apply = apply_rx.search(text)
        if m_apply:
            return ("🚀", m_apply.group(1), "", status, warn_err)
        if "No changes. Your infrastructure matches the configuration." in text:
            return ("✅", "No changes", "", status, warn_err)
        if warn_err:
            return ("⚠️", warn_err.splitlines()[0][:200], "", status, warn_err)
        return ("⚠️", "No apply summary found", "", status, warn_err)

    # plan
    if "No changes. Your infrastructure matches the configuration." in text:
        return ("✅", "No changes", "", status, warn_err)

    m_plan = plan_rx.search(text)
    if m_plan:
        summary = m_plan.group(1)
        plan_block = extract_plan_block(text, summary)
        return ("✏️", summary, plan_block, status, warn_err)

    if warn_err:
        return ("⚠️", warn_err.splitlines()[0][:200], "", status, warn_err)

    return ("⚠️", "No plan summary found", "", status, warn_err)

def final_apply_status_line():
    if mode != "apply":
        return ""
    if run_outcome == "success":
        return "✅ Apply finished successfully"
    if run_outcome == "failure":
        return "❌ Apply failed"
    if run_outcome == "cancelled":
        return "⛔ Apply cancelled"
    if run_outcome == "skipped":
        return "⏭️ Apply skipped"
    return ""

# Build Markdown
lines = []
lines.append(f"## {mode_icon} Terragrunt {mode_label} summary\n")

final_status = final_apply_status_line()
if final_status:
    lines.append(f"**Result:** {final_status}\n")

if step_url:
    lines.append(f"**Step URL:** {step_url}\n")

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

    for short, (icon, summary, plan_block, status, warn_err) in per_unit.items():
        show_any = bool(status or warn_err or (mode == "plan" and plan_block))
        if not show_any:
            continue

        lines.append(f"<details><summary><b>{icon} {short}</b></summary>\n")

        if mode == "plan":
            # ✅ merge status + warnings + plan changes into one details body
            merged_parts = []
            if status:
                merged_parts.append(status)
            if warn_err:
                merged_parts.append("Warnings/Errors:\n" + warn_err)
            if plan_block:
                merged_parts.append(plan_block)

            merged = "\n\n".join(p for p in merged_parts if p).strip()
            if merged:
                lines.append("```diff")
                lines.append(clip(merged, 16000).rstrip())
                lines.append("```\n")
        else:
            # ✅ apply: only status + warnings, no plan changes
            body_parts = []
            if status:
                body_parts.append(status)
            if warn_err:
                body_parts.append("Warnings/Errors:\n" + warn_err)

            body = "\n\n".join(p for p in body_parts if p).strip()
            if body:
                lines.append("```text")
                lines.append(clip(body, 8000).rstrip())
                lines.append("```\n")

        lines.append("</details>\n")

out = "\n".join(lines).rstrip() + "\n"
out = clip(out, limit)

print("summary<<EOF")
print(out)
print("EOF")