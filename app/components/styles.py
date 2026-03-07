"""
Dark command-center CSS theme for Startup Brain.
Exports inject_custom_css() which injects all styles via st.markdown.
"""

import streamlit as st


def inject_custom_css():
    # Load fonts via <link> tag — more reliable than @import in Safari
    st.markdown(
        '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700'
        '&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )
    st.markdown("""<style>
/* ===== 1. Google Fonts — Space Grotesk + IBM Plex Mono (loaded via <link> above) ===== */

/* ===== 2. CSS Variables ===== */
:root {
    --bg-primary: #0D1117;
    --bg-surface: #161B22;
    --bg-elevated: #1C2333;
    --border-default: #30363D;
    --border-hover: #484F58;
    --text-primary: #E6EDF3;
    --text-secondary: #8B949E;
    --accent-blue: #58A6FF;
    --accent-cyan: #39D2C0;
    --accent-green: #3FB950;
    --accent-yellow: #D29922;
    --accent-red: #F85149;
    --accent-purple: #BC8CFF;
    --font-display: 'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --font-mono: 'IBM Plex Mono', 'JetBrains Mono', 'Fira Code', monospace;
    --glow-blue: 0 0 20px rgba(88,166,255,0.15);
    --glow-cyan: 0 0 20px rgba(57,210,192,0.12);
}

/* ===== 3. Global dark overrides ===== */
.stApp,
.main .block-container,
[data-testid="stAppViewContainer"],
[data-testid="stAppViewBlockContainer"],
[data-testid="stVerticalBlock"],
[data-testid="stMain"] {
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

header[data-testid="stHeader"] {
    background-color: var(--bg-primary) !important;
    border-bottom: none !important;
}

html, body, .stApp, .stMarkdown, .stMarkdown p, .stMarkdown li,
.stMarkdown span, .stText, [data-testid="stText"],
label, .stRadio label, .stSelectbox label, .stTextInput label,
.stTextArea label, .stNumberInput label {
    font-family: var(--font-display) !important;
    color: var(--text-primary) !important;
}

code, pre, .stCode, [data-testid="stCode"] {
    font-family: var(--font-mono) !important;
}

h1, .stMarkdown h1 {
    color: var(--text-primary) !important;
    font-family: var(--font-display) !important;
    font-weight: 700 !important;
    letter-spacing: -0.03em !important;
}

h2, .stMarkdown h2 {
    color: var(--accent-blue) !important;
    font-family: var(--font-display) !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
    font-size: 1.35rem !important;
    border-bottom: 1px solid var(--border-default) !important;
    padding-bottom: 0.4rem !important;
}

h3, .stMarkdown h3 {
    color: var(--accent-cyan) !important;
    font-family: var(--font-display) !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
    font-size: 1.1rem !important;
}

h4, h5, h6,
.stMarkdown h4, .stMarkdown h5, .stMarkdown h6 {
    color: var(--text-primary) !important;
    font-family: var(--font-display) !important;
    font-weight: 600 !important;
}

/* ===== 4. Hide sidebar entirely ===== */
section[data-testid="stSidebar"] {
    display: none !important;
}

button[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {
    display: none !important;
}

/* ===== 5. Top bar styling ===== */
.top-bar-title {
    font-family: var(--font-display) !important;
    font-weight: 700;
    font-size: 1.4rem;
    letter-spacing: -0.03em;
    color: var(--text-primary);
    margin: 0;
    line-height: 1.2;
}

.top-bar-subtitle {
    font-family: var(--font-display) !important;
    font-size: 0.75rem;
    color: var(--accent-cyan);
    margin: 0;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-weight: 500;
}

.status-pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 500;
    font-family: var(--font-mono) !important;
    background-color: var(--bg-elevated);
    color: var(--text-secondary);
    border: 1px solid var(--border-default);
    letter-spacing: 0.01em;
}

/* ===== 7. Tab navigation styling (st.radio horizontal) ===== */
div[data-testid="stHorizontalBlock"] .stRadio > div {
    display: flex !important;
    flex-direction: row !important;
    gap: 0 !important;
    background-color: var(--bg-surface) !important;
    border-bottom: 1px solid var(--border-default) !important;
    padding: 0 !important;
    border-radius: 8px 8px 0 0 !important;
}

div[data-testid="stHorizontalBlock"] .stRadio > div > label {
    padding: 0.6rem 1.5rem !important;
    border-bottom: 2px solid transparent !important;
    cursor: pointer !important;
    color: var(--text-secondary) !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    font-family: var(--font-display) !important;
    letter-spacing: -0.01em !important;
    transition: color 0.2s ease, border-color 0.2s ease, background-color 0.2s ease !important;
    background-color: transparent !important;
    margin: 0 !important;
}

div[data-testid="stHorizontalBlock"] .stRadio > div > label:hover {
    color: var(--text-primary) !important;
    background-color: rgba(88,166,255,0.04) !important;
}

div[data-testid="stHorizontalBlock"] .stRadio > div > label[data-checked="true"],
div[data-testid="stHorizontalBlock"] .stRadio > div > label:has(input:checked) {
    color: var(--accent-blue) !important;
    border-bottom-color: var(--accent-blue) !important;
    font-weight: 600 !important;
}

/* Hide radio circles */
div[data-testid="stHorizontalBlock"] .stRadio > div > label > div:first-child {
    display: none !important;
}

/* ===== 8. Dark chat message styling ===== */
.stChatMessage,
[data-testid="stChatMessage"] {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: 12px !important;
    padding: 1rem 1.5rem !important;
    margin-bottom: 0.5rem !important;
    color: var(--text-primary) !important;
    transition: border-color 0.2s ease !important;
}

.stChatMessage:hover,
[data-testid="stChatMessage"]:hover {
    border-color: var(--border-hover) !important;
}

/* User messages: slightly elevated shade */
[data-testid="stChatMessage"][data-testid*="user"] {
    background-color: var(--bg-elevated) !important;
}

[data-testid="stChatMessageContent"] p,
[data-testid="stChatMessageContent"] li,
[data-testid="stChatMessageContent"] span {
    color: var(--text-primary) !important;
}

/* Chat input */
[data-testid="stChatInput"],
[data-testid="stChatInput"] textarea {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border-default) !important;
    color: var(--text-primary) !important;
    border-radius: 8px !important;
    font-family: var(--font-display) !important;
}

[data-testid="stChatInput"] textarea:focus {
    border-color: var(--accent-blue) !important;
    box-shadow: var(--glow-blue) !important;
}

/* Chat frame — bordered container styling */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: var(--border-default) !important;
    border-radius: 10px !important;
    background-color: var(--bg-surface) !important;
    min-height: 420px;
}

/* Force chat message content to full width during streaming */
[data-testid="stChatMessageContent"] {
    width: 100% !important;
    min-height: 1.5em;
}
[data-testid="stChatMessageContent"] > div {
    width: 100% !important;
}

/* ===== 9. Step indicator styling ===== */
.step-indicator {
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 1rem 0;
    gap: 0;
}

.step-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    position: relative;
}

.step-circle {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-primary);
    z-index: 1;
    font-family: var(--font-display);
    transition: all 0.3s ease;
}

.step-circle.completed {
    background-color: var(--accent-green);
    color: #ffffff;
    box-shadow: 0 0 8px rgba(63,185,80,0.3);
}

.step-circle.active {
    background-color: var(--accent-blue);
    color: #ffffff;
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.25), var(--glow-blue);
    animation: pulse-active 2s infinite;
}

@keyframes pulse-active {
    0%, 100% { box-shadow: 0 0 0 3px rgba(88,166,255,0.25); }
    50% { box-shadow: 0 0 0 5px rgba(88,166,255,0.15), 0 0 20px rgba(88,166,255,0.1); }
}

.step-circle.pending {
    background-color: var(--border-default);
    color: var(--text-secondary);
}

.step-connector {
    width: 60px;
    height: 2px;
    margin-top: 15px;
    flex-shrink: 0;
}

.step-connector.completed {
    background-color: var(--accent-green);
}

.step-connector.pending {
    background-color: var(--border-default);
}

.step-label {
    font-size: 0.72rem;
    color: var(--text-secondary);
    margin-top: 6px;
    text-align: center;
    white-space: nowrap;
    font-family: var(--font-display);
}

.step-label.active {
    color: var(--accent-blue);
    font-weight: 600;
}

.step-label.completed {
    color: var(--accent-green);
}

/* ===== 12. Severity badges (dark theme) ===== */
.severity-critical {
    background-color: rgba(248, 81, 73, 0.1);
    border-left: 4px solid var(--accent-red);
    padding: 1rem;
    border-radius: 4px;
    margin: 0.5rem 0;
    color: var(--text-primary);
}

.severity-notable {
    background-color: rgba(210, 153, 34, 0.1);
    border-left: 4px solid var(--accent-yellow);
    padding: 1rem;
    border-radius: 4px;
    margin: 0.5rem 0;
    color: var(--text-primary);
}

/* ===== 13. Pill badges (dark theme) ===== */
.pill-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.8rem;
    margin: 2px;
    font-weight: 500;
    font-family: var(--font-display);
}

.pill-badge-yellow {
    background-color: rgba(210, 153, 34, 0.12);
    color: var(--accent-yellow);
}

.pill-badge-blue {
    background-color: rgba(88, 166, 255, 0.12);
    color: var(--accent-blue);
}

/* ===== 14. Hypothesis badges (dark theme) ===== */
.hypothesis-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.75rem;
    margin: 2px;
    font-weight: 600;
    font-family: var(--font-display);
}

.hypothesis-unvalidated {
    background-color: rgba(210, 153, 34, 0.12);
    color: var(--accent-yellow);
}

.hypothesis-validated {
    background-color: rgba(63, 185, 80, 0.12);
    color: var(--accent-green);
}

.hypothesis-invalidated {
    background-color: rgba(248, 81, 73, 0.12);
    color: var(--accent-red);
}

/* ===== 15. Button overrides ===== */
/* Primary action buttons (Ingest Session, form submits, etc.) */
button[kind="primary"] {
    background-color: var(--accent-blue) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-family: var(--font-display) !important;
    letter-spacing: -0.01em !important;
    transition: background-color 0.2s ease !important;
}

button[kind="primary"]:hover {
    background-color: #79B8FF !important;
    color: #ffffff !important;
}

/* Default buttons — ghost/outline style (suggestion chips, quick commands) */
.stButton > button {
    background-color: transparent !important;
    color: var(--text-secondary) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: 999px !important;
    font-weight: 500 !important;
    font-family: var(--font-display) !important;
    font-size: 0.8rem !important;
    letter-spacing: -0.01em !important;
    padding: 0.3rem 0.8rem !important;
    transition: color 0.15s ease, border-color 0.15s ease, background-color 0.15s ease !important;
    min-height: 0 !important;
    line-height: 1.4 !important;
}

.stButton > button:hover {
    color: var(--text-primary) !important;
    border-color: var(--border-hover) !important;
    background-color: var(--bg-surface) !important;
}

/* Secondary button explicit style */
.stButton > button[kind="secondary"],
button[kind="secondary"] {
    background-color: var(--bg-surface) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border-default) !important;
}

.stButton > button[kind="secondary"]:hover,
button[kind="secondary"]:hover {
    background-color: var(--bg-elevated) !important;
    border-color: var(--border-hover) !important;
}

/* Top bar & dashboard action buttons — filled style (not ghost) */
.stButton > button[kind="primary"] {
    background-color: var(--accent-blue) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.5rem 1rem !important;
    font-size: 0.88rem !important;
    font-weight: 600 !important;
}

.stButton > button[kind="primary"]:hover {
    background-color: #79B8FF !important;
}

/* ===== 16. Form input overrides ===== */
input, textarea, select,
.stTextInput input,
.stTextArea textarea,
.stSelectbox select,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
.stSelectbox [data-baseweb="select"],
[data-baseweb="select"],
[data-baseweb="input"] {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border-default) !important;
    color: var(--text-primary) !important;
    border-radius: 8px !important;
    font-family: var(--font-display) !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

input:focus, textarea:focus, select:focus,
.stTextInput input:focus,
.stTextArea textarea:focus,
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: var(--accent-blue) !important;
    box-shadow: var(--glow-blue) !important;
}

/* Dropdown menus */
[data-baseweb="popover"],
[data-baseweb="menu"],
[data-baseweb="list"] {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border-default) !important;
}

[data-baseweb="menu"] li,
[data-baseweb="list"] li {
    color: var(--text-primary) !important;
}

[data-baseweb="menu"] li:hover,
[data-baseweb="list"] li:hover {
    background-color: var(--bg-elevated) !important;
}

/* ===== 17. Expander overrides ===== */
.streamlit-expanderHeader,
[data-testid="stExpander"],
details, summary {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: 8px !important;
    color: var(--text-primary) !important;
    transition: border-color 0.2s ease !important;
}

[data-testid="stExpander"]:hover,
details:hover {
    border-color: var(--border-hover) !important;
}

[data-testid="stExpander"] > details > div {
    background-color: var(--bg-surface) !important;
}

/* ===== 18. Dividers ===== */
hr, .stDivider,
[data-testid="stDivider"] {
    border-color: var(--border-default) !important;
}

/* ===== 19. Hide Streamlit menu and footer ===== */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header .decoration { display: none !important; }

/* ===== 20. Metric styling ===== */
[data-testid="stMetric"],
[data-testid="stMetricValue"],
[data-testid="stMetricLabel"] {
    color: var(--text-primary) !important;
}

[data-testid="stMetricValue"] {
    font-weight: 700 !important;
    font-family: var(--font-display) !important;
    letter-spacing: -0.02em !important;
}

[data-testid="stMetricDelta"] {
    font-family: var(--font-display) !important;
}

/* ===== 21. Dark st.info/success/warning/error overrides ===== */
[data-testid="stAlert"],
.stAlert,
div[data-testid="stNotification"] {
    border-radius: 8px !important;
    font-family: var(--font-display) !important;
}

/* st.info */
div[data-testid="stAlert"][data-baseweb*="info"],
.element-container .stAlert:has([data-testid="stAlertContentInfo"]),
div[role="alert"].st-emotion-cache-info,
[data-testid="stNotification"][data-type="info"] {
    background-color: rgba(88, 166, 255, 0.08) !important;
    border-left: 4px solid var(--accent-blue) !important;
    color: var(--text-primary) !important;
}

/* st.success */
div[data-testid="stAlert"][data-baseweb*="positive"],
.element-container .stAlert:has([data-testid="stAlertContentSuccess"]),
div[role="alert"].st-emotion-cache-success,
[data-testid="stNotification"][data-type="success"] {
    background-color: rgba(63, 185, 80, 0.08) !important;
    border-left: 4px solid var(--accent-green) !important;
    color: var(--text-primary) !important;
}

/* st.warning */
div[data-testid="stAlert"][data-baseweb*="warning"],
.element-container .stAlert:has([data-testid="stAlertContentWarning"]),
div[role="alert"].st-emotion-cache-warning,
[data-testid="stNotification"][data-type="warning"] {
    background-color: rgba(210, 153, 34, 0.08) !important;
    border-left: 4px solid var(--accent-yellow) !important;
    color: var(--text-primary) !important;
}

/* st.error */
div[data-testid="stAlert"][data-baseweb*="negative"],
.element-container .stAlert:has([data-testid="stAlertContentError"]),
div[role="alert"].st-emotion-cache-error,
[data-testid="stNotification"][data-type="error"] {
    background-color: rgba(248, 81, 73, 0.08) !important;
    border-left: 4px solid var(--accent-red) !important;
    color: var(--text-primary) !important;
}

/* Alert text inside all notification types */
[data-testid="stAlert"] p,
[data-testid="stNotification"] p,
.stAlert p {
    color: var(--text-primary) !important;
}

/* ===== 22. Scrollbar styling ===== */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background: var(--border-default);
    border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--text-secondary);
}

/* ===== 23. Chat-centric welcome screen ===== */
.welcome-container {
    text-align: center;
    padding: 0 1rem 0.5rem;
}

.welcome-tagline {
    color: var(--text-secondary);
    font-family: var(--font-display);
    font-size: 0.95rem;
    font-weight: 400;
    margin-bottom: 0;
}

.welcome-emphasis {
    color: rgba(57, 210, 192, 0.5);
    font-family: var(--font-display);
    font-size: 0.7rem;
    font-weight: 500;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 0.5rem;
}

/* ===== 24. Responsive breakpoints ===== */
@media (max-width: 1440px) {
    .main .block-container {
        max-width: 95% !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
}

@media (max-width: 1200px) {
    .top-bar-title {
        font-size: 1.2rem;
    }

    .status-pill {
        font-size: 0.68rem;
        padding: 2px 8px;
    }
}

/* ===== 25. Mobile (iPhone) breakpoint ===== */
@media (max-width: 480px) {
    .step-connector {
        width: 24px;
    }

    .step-circle {
        width: 26px;
        height: 26px;
        font-size: 0.75rem;
    }

    .step-label {
        font-size: 0.65rem;
    }

    .top-bar-title {
        font-size: 1rem;
    }

    .top-bar-subtitle {
        font-size: 0.65rem;
    }

    .status-pill {
        font-size: 0.62rem;
        padding: 2px 6px;
    }

    .stButton > button {
        min-height: 40px !important;
        padding: 0.5rem 0.8rem !important;
    }
}
</style>""", unsafe_allow_html=True)
