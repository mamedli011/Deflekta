"""Invisible-Injection Shield dashboard (Role 1).

Run from the repo root:  streamlit run frontend/app.py

R1-T1: timeline of agent events from contracts/sample_events.jsonl
(or any saved run in runs/). No agent import yet; that comes in R1-T2.
Colors: ALLOWED green; FLAGGED / NEEDS_CONFIRM yellow; STRIPPED / BLOCKED red.
"""
import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_FILE = ROOT / "contracts" / "sample_events.jsonl"
RUNS_DIR = ROOT / "runs"

# Streamlit markdown color for each verdict (used in badges and labels)
VERDICT_COLOR = {
    "ALLOWED": "green",
    "FLAGGED": "yellow",
    "NEEDS_CONFIRM": "yellow",
    "STRIPPED": "red",
    "BLOCKED": "red",
}

DEFAULT_TASK = "Find the pasta recipe on this page and email it to me."

st.set_page_config(page_title="Invisible-Injection Shield", page_icon="🛡️", layout="wide")

# Light styling: monospace for machine data, tighter headings.
st.markdown(
    """
    <style>
      code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
      div[data-testid="stExpander"] summary p { font-size: 0.92rem; }
      .run-head { display:flex; gap:10px; align-items:center; margin: 0.6rem 0 0.3rem; }
      .tag { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 0.75rem;
             padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(148,163,184,.45);
             color: rgba(148,163,184,1); }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------- data helpers ----------------

@st.cache_data
def load_jsonl(path: str) -> list[dict]:
    """Read one JSON event per line. Skips blank lines."""
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def saved_run_files() -> list[Path]:
    """Sample file first, then any saved runs in runs/."""
    files = [SAMPLE_FILE] if SAMPLE_FILE.exists() else []
    if RUNS_DIR.exists():
        files += sorted(RUNS_DIR.glob("*.jsonl"))
    return files


def group_by_run(events: list[dict]) -> dict[str, list[dict]]:
    """Keep runs in the order they first appear; sort events by time inside each run."""
    runs: dict[str, list[dict]] = {}
    for ev in events:
        runs.setdefault(ev.get("session_id", "unknown"), []).append(ev)
    for evs in runs.values():
        evs.sort(key=lambda e: e.get("timestamp", ""))
    return runs


# ---------------- display helpers ----------------

def badge(verdict: str) -> str:
    color = VERDICT_COLOR.get(verdict, "gray")
    return f":{color}-background[**{verdict}**]"


def short_time(ev: dict) -> str:
    ts = ev.get("timestamp", "")
    return ts[11:19] if len(ts) >= 19 else ts or "--:--:--"


def row_label(ev: dict) -> str:
    """One line per event: time, stage, tool, verdict badge, reason."""
    tool = ev.get("tool") or "-"
    reason = ev.get("reason") or ""
    return (f"`{short_time(ev)}` · `{ev.get('stage', '?')}` · `{tool}` · "
            f"{badge(ev.get('verdict', '?'))} · {reason}")


def show_event_details(ev: dict) -> None:
    """Body of an expanded row: rule, layer, args, evidence."""
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**Rule**  \n`{ev.get('rule_triggered') or 'none'}`")
    c2.markdown(f"**Layer**  \n`{ev.get('layer') if ev.get('layer') is not None else 'none'}`")
    c3.markdown(f"**Severity**  \n`{ev.get('severity') or 'none'}`")

    hidden = (ev.get("evidence") or {}).get("hidden_text")
    if hidden:
        st.markdown("**Hidden text found on the page**")
        st.error(hidden, icon="👁️")

    st.markdown("**args**")
    if ev.get("tool") == "send_email":
        st.caption("Fake bait data from the test setup. No real account is involved.")
    st.json(ev.get("args") or {}, expanded=True)

    st.markdown("**evidence**")
    st.json(ev.get("evidence") or {}, expanded=True)

    if ev.get("result"):
        st.markdown("**result**")
        st.code(str(ev["result"]), language=None)


# ---------------- state ----------------

if "events" not in st.session_state:
    st.session_state.events = load_jsonl(str(SAMPLE_FILE)) if SAMPLE_FILE.exists() else []
    st.session_state.source = "contracts/sample_events.jsonl"
    st.session_state.notice = None


# ---------------- sidebar ----------------

with st.sidebar:
    st.subheader("Controls")
    shield_on = st.toggle("Shield ON", value=True)
    task = st.text_area("Task for the agent", value=DEFAULT_TASK, height=90)
    if st.button("Run agent", type="primary"):
        st.session_state.notice = ("Live runs connect to the agent in R1-T2. "
                                   "Use a saved run below for now.")

    st.divider()
    files = saved_run_files()
    if files:
        choice = st.selectbox(
            "Replay saved run",
            files,
            format_func=lambda p: str(p.relative_to(ROOT)).replace("\\", "/"),
        )
        if st.button("Replay"):
            st.session_state.events = load_jsonl(str(choice))
            st.session_state.source = str(choice.relative_to(ROOT)).replace("\\", "/")
            st.session_state.notice = None
    else:
        st.caption("No saved runs found.")


# ---------------- main area ----------------

st.title("Invisible-Injection Shield")
st.caption("What the AI agent did on each step, and what the shield decided.")

if st.session_state.notice:
    st.info(st.session_state.notice)

events = st.session_state.events
if not events:
    st.warning("No events to show. Check that contracts/sample_events.jsonl exists.")
    st.stop()

runs = group_by_run(events)

# Summary of what's on screen (counted from the events, not typed by hand)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Runs", len(runs))
m2.metric("Events", len(events))
m3.metric("Hidden text stripped", sum(e.get("verdict") == "STRIPPED" for e in events))
m4.metric("Actions blocked", sum(e.get("verdict") == "BLOCKED" for e in events))

st.markdown(f'<span class="tag">SOURCE: {st.session_state.source}</span> '
            f'<span class="tag">MODE: REPLAY</span>', unsafe_allow_html=True)

for session_id, evs in runs.items():
    shield_state = evs[0].get("shield_on")
    shield_text = "Shield ON" if shield_state else "Shield OFF" if shield_state is False else "Shield ?"
    st.markdown(f"#### {shield_text} &nbsp; `{session_id}`")
    for ev in evs:
        with st.expander(row_label(ev)):
            show_event_details(ev)