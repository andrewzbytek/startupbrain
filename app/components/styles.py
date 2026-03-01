"""
Custom CSS injection for Startup Brain.
"""

import streamlit as st


def inject_custom_css():
    st.markdown("""<style>
    /* Chat messages */
    .stChatMessage { padding: 1rem 1.5rem; border-radius: 12px; margin-bottom: 0.5rem; }

    /* Severity banners */
    .severity-critical { background-color: #FEE2E2; border-left: 4px solid #DC2626; padding: 1rem; border-radius: 4px; margin: 0.5rem 0; }
    .severity-notable { background-color: #FEF3C7; border-left: 4px solid #D97706; padding: 1rem; border-radius: 4px; margin: 0.5rem 0; }

    /* Pill badges for themes */
    .pill-badge { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.8rem; margin: 2px; }
    .pill-badge-red { background-color: #FEE2E2; color: #991B1B; }
    .pill-badge-yellow { background-color: #FEF3C7; color: #92400E; }
    .pill-badge-blue { background-color: #DBEAFE; color: #1E40AF; }

    /* Hide Streamlit menu and footer */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Claim row styling */
    .claim-row { border-bottom: 1px solid #E5E7EB; padding: 8px 0; }

    /* Status indicators */
    .status-green { color: #22C55E; }
    .status-white { color: #D1D5DB; }
    </style>""", unsafe_allow_html=True)
