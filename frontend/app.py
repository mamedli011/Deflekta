"""Streamlit dashboard (Role 1).

Run: streamlit run frontend/app.py
R1-T1: works on contracts/sample_events.jsonl so the UI can be built
before the agent works.
Colors: ALLOWED green; FLAGGED / NEEDS_CONFIRM yellow; STRIPPED / BLOCKED red.
"""
import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_FILE = ROOT / "contracts" / "sample_events.jsonl"

COLORS = {
    "ALLOWED": "#15803d",        # green
    "FLAGGED": "#b45309",        # yellow / amber
    "NEEDS_CONFIRM": "#b45309",  # yellow / amber
    "STRIPPED": "#b91c1c",       # red
    "BLOCKED": "#b91c1c",        # red
}
OTHER_COLOR = "#6b7280"          # grey for anything unknown

DEFAULT_TASK = "Find the pasta recipe on this page and email it to me."


# ---------- helpers ----------

@st.cache_data
def load_events(path: str) -> list[dict]:
    """Read a .jsonl file: one JSON event per line."""
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def badge(verdict: str) -> str:
    """Small colored label for a verdict."""
    color = COLORS.get(verdict, OTHER_COLOR)
    return (
        f'<span style="background:{color};color:#fff;padding:2px 10px;'
        f'border-radius:4px;font-weight:600;font-size:0.8rem">{verdict}</span>'
    )


def title_of(ev: dict) -> str:
    """Short, readable name for an event."""
    if ev.get("stage") == "final":
        return "Final answer"
    tool = ev.get("tool") or "no tool"
    return f"{tool} ({ev.get('stage', '?')})"


def time_of(ev: dict) -> str:
    ts = ev.get("timestamp", "")
    return ts[11:19] if len(ts) >= 19 else ts


# ---------- page setup ----------

st.set_page_config(page_title="Invisible-Injection Shield", page_icon="🛡️", layout="wide")
st.title("🛡️ Invisible-Injection Shield")
st.caption("Watch what an AI agent does on a web page, with and without the shield.")

if "shown_shield" not in st.session_state:
    st.session_state.shown_shield = None   # which run is on screen
    st.session_state.selected = None       # which event is clicked

# ---------- controls (left sidebar) ----------

with st.sidebar:
    st.header("Controls")
    shield_on = st.toggle("Shield on", value=True)
    task = st.text_area("Task for the AI", value=DEFAULT_TASK, height=100)
    if st.button("Run", type="primary"):
        st.session_state.shown_shield = shield_on
        st.session_state.selected = None
    st.caption("Sample data mode: shows the saved sample run. Live runs come in R1-T2.")

# ---------- load data ----------

if not SAMPLE_FILE.exists():
    st.error(f"Can't find {SAMPLE_FILE}. Run the app from the repo folder.")
    st.stop()

if st.session_state.shown_shield is None:
    st.info("Turn the shield on or off, then press Run.")
    st.stop()

all_events = load_events(str(SAMPLE_FILE))
events = [e for e in all_events if e.get("shield_on") == st.session_state.shown_shield]
events.sort(key=lambda e: e.get("timestamp", ""))

label = "ON" if st.session_state.shown_shield else "OFF"
st.subheader(f"Run with shield {label}")

if not events:
    st.warning("No sample events for this setting.")
    st.stop()

# ---------- timeline (left) + details (right) ----------

left, right = st.columns([3, 2], gap="large")

with left:
    st.markdown("#### Timeline")
    for ev in events:
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(
                    f"`{time_of(ev)}` &nbsp; {badge(ev.get('verdict', '?'))} &nbsp; "
                    f"**{title_of(ev)}**",
                    unsafe_allow_html=True,
                )
                st.caption(ev.get("reason") or "")
            with c2:
                if st.button("Details", key=f"btn_{ev['id']}"):
                    st.session_state.selected = ev["id"]

with right:
    st.markdown("#### Event details")
    chosen = next((e for e in events if e["id"] == st.session_state.selected), None)
    if chosen is None:
        st.caption("Click Details on any event to see it here.")
    else:
        st.markdown(badge(chosen.get("verdict", "?")), unsafe_allow_html=True)
        st.markdown(f"**{title_of(chosen)}** at `{time_of(chosen)}`")
        st.write(chosen.get("reason") or "")

        info = {
            "Stage": chosen.get("stage"),
            "Tool": chosen.get("tool"),
            "Shield layer": chosen.get("layer"),
            "Rule": chosen.get("rule_triggered"),
            "Severity": chosen.get("severity"),
        }
        for k, v in info.items():
            if v is not None:
                st.markdown(f"- **{k}:** {v}")

        hidden = (chosen.get("evidence") or {}).get("hidden_text")
        if hidden:
            st.markdown("**Hidden text found on the page:**")
            st.markdown(
                f'<div style="border-left:4px solid {COLORS["BLOCKED"]};'
                f'padding:8px 12px;color:{COLORS["BLOCKED"]}">{hidden}</div>',
                unsafe_allow_html=True,
            )

        if chosen.get("args"):
            st.markdown("**What the AI tried to do:**")
            st.json(chosen["args"])
        if chosen.get("evidence"):
            st.markdown("**Evidence:**")
            st.json(chosen["evidence"])
        if chosen.get("result"):
            st.markdown("**Result:**")
            st.code(str(chosen["result"]), language=None)