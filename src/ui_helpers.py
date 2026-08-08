from __future__ import annotations

import html as html_mod
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

import database as db

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
LOGO_HORIZONTAL_WHITE_SVG = ASSETS_DIR / "logo-horizontal-white.svg"
LOGO_HORIZONTAL_WHITE_PNG = ASSETS_DIR / "logo-horizontal-white.png"
LOGO_HORIZONTAL_BLACK_SVG = ASSETS_DIR / "logo-horizontal-black.svg"
LOGO_HORIZONTAL_BLACK_PNG = ASSETS_DIR / "logo-horizontal-black.png"
LOGO_HORIZONTAL_SVG = LOGO_HORIZONTAL_WHITE_SVG if LOGO_HORIZONTAL_WHITE_SVG.exists() else ASSETS_DIR / "logo-horizontal.svg"
LOGO_HORIZONTAL_PNG = LOGO_HORIZONTAL_WHITE_PNG if LOGO_HORIZONTAL_WHITE_PNG.exists() else ASSETS_DIR / "logo-horizontal.png"
LOGO_MARK_SVG = ASSETS_DIR / "logo-mark.svg"
FAVICON_PNG = ASSETS_DIR / "favicon.png"

STATUS_LABELS = {"backlog": "Backlog", "played": "Played", "abandoned": "Abandoned"}

@st.cache_data(ttl=30)
def cached_list_tags() -> list[dict[str, Any]]:
    """Cached wrapper to avoid re-querying tags on every render."""
    return db.list_tags()

def clear_tags_cache() -> None:
    cached_list_tags.clear()

def queue_toast(message: str, icon: str = "") -> None:
    """Store a toast in session_state so it fires AFTER the next st.rerun().

    Call this instead of st.toast() whenever a st.rerun() follows immediately.
    The deferred toast is shown at the very start of the next render by
    show_queued_toasts(), before any rerun can clobber it.
    """
    if "pending_toasts" not in st.session_state:
        st.session_state["pending_toasts"] = []
    st.session_state["pending_toasts"].append({"message": message, "icon": icon})

def show_queued_toasts() -> None:
    """Display any toasts queued by queue_toast(). Call once at app startup."""
    for toast in st.session_state.pop("pending_toasts", []):
        if toast.get("icon"):
            st.toast(toast["message"], icon=toast["icon"])
        else:
            st.toast(toast["message"])

def inject_styles() -> None:
    st.markdown(
        """
        <style>
          .block-container { max-width: 1500px; padding-top: 1.4rem; }
          .game-placeholder {aspect-ratio: 3 / 4; width: 100%; display:flex; flex-direction:column; align-items:center;
            justify-content:center; border-radius:.55rem; color:#d7e3f5; background:linear-gradient(145deg,#24334d,#121b2b); font-size:.9rem;}
          .game-placeholder small {font-size:.78rem; margin-top:.55rem; color:#aebed2;}
          .tag-chip {display:inline-block; margin:.2rem .4rem .2rem 0; padding:.12rem .55rem; border-radius:999px;
            background:#27374d; color:#ffffff; font-size:.78rem; font-weight:500; text-shadow:0px 1px 2px rgba(0,0,0,0.6);
            white-space: nowrap; text-overflow: ellipsis; max-width: 150px; overflow: hidden;
            line-height: 1.5; vertical-align: middle; box-sizing: border-box;}
          .muted {color:#9aa8ba; font-size:.86rem;}

          /* Utility & Component Classes */
          .card-title {display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; font-weight: bold; line-height: 1.4; height: 1.4em; margin-bottom: 0.5rem;}
          .card-detail {font-size: 0.86rem; color: #9aa8ba; margin-bottom: 0.3rem; min-height: 1.3em; line-height: 1.5;}
          .status-inline-played {color: #4ade80; font-weight: 500;}
          .status-inline-abandoned {color: #ef4444; font-weight: 500;}
          .status-inline-ready {color: #60a5fa; font-weight: 500;}
          .tag-overflow-dropdown {position: absolute; bottom: 120%; right: 0; background: #0b1423; padding: 0.5rem; border: 1px solid #1a2536; border-radius: 0.4rem; z-index: 9999; display: flex; flex-wrap: wrap; width: max-content; max-width: 220px; box-shadow: 0 4px 6px rgba(0,0,0,0.5);}
          .pagination-label {text-align: center; padding-top: 0.5rem;}
          .col-header-center {text-align: center; font-weight: bold;}

          [data-testid="stImage"] img {aspect-ratio: 3 / 4 !important; width:100% !important; height: auto !important; object-fit:cover; border-radius:.55rem;}
          [data-testid="stSidebar"] [data-testid="stImage"] img,
          .app-logo img {
            aspect-ratio: auto !important;
            width: auto !important;
            max-width: 100% !important;
            height: auto !important;
            object-fit: contain !important;
            border-radius: 0 !important;
            margin: 0 auto;
            display: block;
          }
          /* Streamlit Logo Sizing Override */
          div:has([data-testid="stSidebarLogo"]) {
            width: 100%;
          }
          [data-testid="stSidebarLogo"] {
            image-rendering: pixelated;
            width: 100%;
            height: auto !important;
          }
          /* Header icon shown when sidebar is collapsed */
          img[data-testid="stHeaderLogo"] {
            width: 32px !important;
            height: 32px !important;
            min-width: 32px !important;
            min-height: 32px !important;
            image-rendering: pixelated !important;
            object-fit: contain !important;
          }
          [data-testid="stFullScreenFrame"] > div > div:first-child {padding: 0.5rem; top: 0 !important;}
          [data-testid="stPopover"] button div[data-testid="stMarkdownContainer"] {display: none;}
          button[data-testid="stPopoverButton"] > div {margin-right:0;}
          button[data-testid="stPopoverButton"] > div > div:first-child {display: none;}
          [data-testid="stPopoverBody"] { padding: 0.25rem 0 !important; }
          [data-testid="stPopoverBody"] .stVerticalBlock { gap: 0 !important; }
          [data-testid="stPopoverBody"] .element-container { margin-bottom: 0 !important; }
          [data-testid="stPopoverBody"] button { margin: 0 !important; padding: 0.35rem 1rem !important; min-height: 2.2rem !important; text-align: left !important; }
          [data-testid="stPopoverBody"] button > div { justify-content: flex-start !important; }
          [data-testid="stColumn"]:has(.special-tags-container) {
            position: relative;
            container-type: inline-size;
          }
          [data-testid="stElementContainer"]:has(.special-tags-container) {
            position: absolute;
            width: calc(100% + 2px - 2rem - 20px);
            top: calc((100cqw + 2px - 2rem)*4/3);
            margin: 10px;
            transform: translateY(calc(-100% - 20px));
            z-index: 10;
          }
          .special-tags-container .tag-chip {
            box-shadow: 0px 2px 5px rgba(0, 0, 0, 0.7);
          }

          /* ── Status Tags Overlay (Top Left inside Image) ── */
          [data-testid="stElementContainer"]:has(.status-played-card),
          [data-testid="stElementContainer"]:has(.status-abandoned-card),
          [data-testid="stElementContainer"]:has(.status-backlog-card) {
            display: none !important;
          }

          [data-testid="stColumn"]:has(.status-tags-container) {
            position: relative;
            container-type: inline-size;
          }
          [data-testid="stElementContainer"]:has(.status-tags-container) {
            position: absolute;
            width: auto;
            top: calc(1rem + 1px);
            left: calc(1rem + 1px);
            margin: 10px;
            z-index: 12;
            padding: 0 !important;
          }
          .status-tags-container {
            display: inline-block;
          }
          .status-tag-played,
          .status-tag-abandoned,
          .status-tag-ready {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            box-shadow: 0px 2px 5px rgba(0, 0, 0, 0.7);
          }
          .status-tag-played {
            background-color: #14381f !important;
            color: #4ade80 !important;
            border: 1px solid rgba(34, 197, 94, 0.4);
          }
          .status-tag-abandoned {
            background-color: #271216 !important;
            color: #ef4444 !important;
            border: 1px solid #6b2228;
          }
          .status-tag-ready {
            background-color: #0f233d !important;
            color: #60a5fa !important;
            border: 1px solid rgba(96, 165, 250, 0.4);
          }

          /* Abandoned card visual distinction */
          [data-testid="stColumn"]:has(.status-abandoned-card) [data-testid="stImage"] img,
          [data-testid="stColumn"]:has(.status-abandoned-card) .game-placeholder {
            filter: grayscale(50%) contrast(85%) opacity(0.8);
            transition: filter 0.3s ease, opacity 0.3s ease;
          }
          [data-testid="stColumn"]:has(.status-abandoned-card):hover [data-testid="stImage"] img,
          [data-testid="stColumn"]:has(.status-abandoned-card):hover .game-placeholder {
            filter: grayscale(20%) contrast(95%) opacity(0.95);
          }
          [data-testid="stColumn"]:has(.status-abandoned-card) > div {
            border-color: rgba(239, 68, 68, 0.35) !important;
            background: #17161b !important;
          }

          /* Played card subtle emerald accent */
          [data-testid="stColumn"]:has(.status-played-card) > div {
            border-color: rgba(16, 185, 129, 0.3) !important;
          }

          /* Custom Sidebar Navigation & Fixed 250px Width when expanded */
          [data-testid="stSidebar"] {
            background-color: #0b1423;
            border-right: 1px solid #1a2536;
          }
          [data-testid="stSidebar"][aria-expanded="true"] {
            width: 250px !important;
            min-width: 250px !important;
            max-width: 250px !important;
          }
          /* Disable sidebar animation on close */
          [data-testid="stSidebar"][aria-expanded="false"],
          [data-testid="stSidebar"][aria-expanded="false"] * {
            transition: none !important;
            animation: none !important;
          }
          /* Remove sidebar resize handle */
          [data-testid="stSidebar"] > :nth-child(2),
          [data-testid="stSidebarResizer"] {
            display: none !important;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button {
            border: none;
            background-color: transparent;
            color: #8b9bb4;
            display: flex;
            justify-content: flex-start;
            align-items: center;
            gap: 0.6rem;
            padding: 0.6rem 0.8rem;
            border-radius: 0.4rem;
            transition: all 0.2s ease;
            box-shadow: none;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button:hover {
            background-color: #172439;
            color: #ffffff;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button > * {
            transition: transform 0.2s ease;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button:hover > * {
            transform: scale(1.05);
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {
            background-color: #1e3152;
            color: #60a5fa;
            border-left: 4px solid #3b82f6;
            border-radius: 0 0.4rem 0.4rem 0;
            font-weight: bold;
          }
          
          /* Red style for delete buttons using wrapper */
          [data-testid="stElementContainer"]:has(.delete-btn-wrapper) {
              display: none;
          }
          [data-testid="stElementContainer"]:has(.delete-btn-wrapper) + [data-testid="stElementContainer"] button {
              background-color: #271216 !important;
              color: #ef4444 !important;
              border: 1px solid #6b2228 !important;
              transition: all 0.2s ease;
          }
          [data-testid="stElementContainer"]:has(.delete-btn-wrapper) + [data-testid="stElementContainer"] button:hover {
              background-color: #ef4444 !important;
              color: #ffffff !important;
              border: 1px solid #ef4444 !important;
          }

          /* ── Toast Notifications ─────────────────────────────────────────── */

          @keyframes toast-slide-in {
            0%   { transform: translateX(120%); opacity: 0; }
            60%  { transform: translateX(-6px);  opacity: 1; }
            80%  { transform: translateX(3px);   opacity: 1; }
            100% { transform: translateX(0);     opacity: 1; }
          }

          @keyframes toast-glow-green {
            0%   { box-shadow: 0 4px 24px rgba(34,197,94,0.0),  0 2px 8px rgba(0,0,0,0.5); }
            40%  { box-shadow: 0 4px 32px rgba(34,197,94,0.55), 0 2px 8px rgba(0,0,0,0.5); }
            100% { box-shadow: 0 4px 16px rgba(34,197,94,0.2),  0 2px 8px rgba(0,0,0,0.4); }
          }

          @keyframes toast-glow-amber {
            0%   { box-shadow: 0 4px 24px rgba(251,191,36,0.0),  0 2px 8px rgba(0,0,0,0.5); }
            40%  { box-shadow: 0 4px 32px rgba(251,191,36,0.55), 0 2px 8px rgba(0,0,0,0.5); }
            100% { box-shadow: 0 4px 16px rgba(251,191,36,0.2),  0 2px 8px rgba(0,0,0,0.4); }
          }

          @keyframes toast-glow-red {
            0%   { box-shadow: 0 4px 24px rgba(239,68,68,0.0),  0 2px 8px rgba(0,0,0,0.5); }
            40%  { box-shadow: 0 4px 32px rgba(239,68,68,0.55), 0 2px 8px rgba(0,0,0,0.5); }
            100% { box-shadow: 0 4px 16px rgba(239,68,68,0.2),  0 2px 8px rgba(0,0,0,0.4); }
          }

          /* Base toast reset */
          [data-testid="stToast"] {
            animation: toast-slide-in 0.45s cubic-bezier(0.22,1,0.36,1) forwards;
            border-radius: 0.6rem !important;
            border: 1px solid rgba(255,255,255,0.08) !important;
            backdrop-filter: blur(12px) !important;
            padding: 0.85rem 1.1rem !important;
            min-width: 280px !important;
            max-width: 380px !important;
            font-size: 0.9rem !important;
            font-weight: 500 !important;
            color: #f0f6ff !important;
          }

          [data-testid="stToast"] p {
            line-height: 1.4 !important;
          }

          /* ── Green toasts: check_circle, restore, cloud_done ── */
          [data-testid="stToast"]:has([data-testid="stIconMaterial"]) {
            background: linear-gradient(135deg, #0f2a1a 0%, #14381f 100%) !important;
            border-color: rgba(34,197,94,0.35) !important;
            animation: toast-slide-in 0.45s cubic-bezier(0.22,1,0.36,1) forwards,
                       toast-glow-green 1.2s 0.45s ease-out forwards !important;
          }

          [data-testid="stToast"]:has([data-testid="stIconMaterial"]) [data-testid="stIconMaterial"] {
            color: #4ade80 !important;
          }

          /* ── Amber toasts: refresh, delete ── */
          [data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="refresh"]),
          [data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="delete"]) {
            background: linear-gradient(135deg, #251e08 0%, #352905 100%) !important;
            border-color: rgba(251,191,36,0.35) !important;
            animation: toast-slide-in 0.45s cubic-bezier(0.22,1,0.36,1) forwards,
                       toast-glow-amber 1.2s 0.45s ease-out forwards !important;
          }

          [data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="refresh"]) [data-testid="stIconMaterial"],
          [data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="delete"]) [data-testid="stIconMaterial"] {
            color: #fbbf24 !important;
          }

          /* ── Red toasts: error, cloud_off ── */
          [data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="error"]),
          [data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="cloud_off"]) {
            background: linear-gradient(135deg, #200d0d 0%, #2e1010 100%) !important;
            border-color: rgba(239,68,68,0.4) !important;
            animation: toast-slide-in 0.45s cubic-bezier(0.22,1,0.36,1) forwards,
                       toast-glow-red 1.2s 0.45s ease-out forwards !important;
          }

          [data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="error"]) [data-testid="stIconMaterial"],
          [data-testid="stToast"]:has([data-testid="stIconMaterial"][aria-label="cloud_off"]) [data-testid="stIconMaterial"] {
            color: #f87171 !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

def readable_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return value

def format_hours(value: float | None) -> str:
    return f"{value:.1f} h" if value is not None else "No duration"

def cover_reference(item: dict[str, Any]) -> str | None:
    path_str = item.get("cover_local_path")
    if path_str:
        # Check in AppData covers directory (%APPDATA%\GameGrimoire\covers\<filename>)
        filename = Path(path_str).name
        candidate_appdata = db.DATA_DIR / "covers" / filename
        if candidate_appdata.exists():
            return str(candidate_appdata)

        # Fallback: check relative to BASE_DIR if legacy path
        candidate_base = db.BASE_DIR / path_str
        if candidate_base.exists():
            return str(candidate_base)
    return item.get("cover_source_url")

def tag_html(tags: Iterable[str], limit: int = 4, show_empty: bool = True) -> str:
    names = list(tags)
    shown = names[:limit]
    hidden = names[limit:]
    
    all_tags = cached_list_tags()
    name_to_color = {t["name"]: t["color"] for t in all_tags}
    
    chips = []
    for name in shown:
        safe_name = html_mod.escape(name)
        safe_color = html_mod.escape(name_to_color.get(name, "#27374d"))
        chips.append(f'<span class="tag-chip" style="background-color: {safe_color};">{safe_name}</span>')
        
    if hidden:
        hidden_chips = []
        for name in hidden:
            safe_name = html_mod.escape(name)
            safe_color = html_mod.escape(name_to_color.get(name, "#27374d"))
            hidden_chips.append(f'<span class="tag-chip" style="background-color: {safe_color}; margin-bottom: 0.2rem;">{safe_name}</span>')
            
        hidden_html = "".join(hidden_chips)
        
        details_html = f'''
        <style>details > summary.overflow-chip::-webkit-details-marker {{ display: none; }} details > summary.overflow-chip::marker {{ display: none; }}</style>
        <details style="display: inline-block; position: relative; vertical-align: middle;">
            <summary class="tag-chip overflow-chip" style="background-color: #4a5568; flex-shrink: 0; cursor: pointer; list-style: none; display: inline-block;">+{len(hidden)}</summary>
            <div class="tag-overflow-dropdown">
                {hidden_html}
            </div>
        </details>
        '''
        chips.append(details_html)
        
    if not chips and not show_empty:
        return ""
        
    inner_html = "".join(chips) or '<span class="muted" style="line-height: 1.2;">No tags</span>'
    return f'<div style="display: flex; flex-wrap: nowrap; align-items: center; width: 100%; min-height: 2rem;">{inner_html}</div>'

ICON_CHECK = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -1px;"><polyline points="20 6 9 17 4 12"></polyline></svg>'
ICON_BAN = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -1px;"><circle cx="12" cy="12" r="10"></circle><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line></svg>'
ICON_BOLT = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -1px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>'

def status_tag_html(status: str, ready_to_play: bool = False) -> str:
    if status == "played":
        return f'<span class="tag-chip status-tag-played">{ICON_CHECK} Played</span>'
    elif status == "abandoned":
        return f'<span class="tag-chip status-tag-abandoned">{ICON_BAN} Abandoned</span>'
    elif status == "backlog" and ready_to_play:
        return f'<span class="tag-chip status-tag-ready">{ICON_BOLT} Ready</span>'
    return ""