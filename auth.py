import hmac
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def accounts():
    return {os.getenv(f"APP_USER{i}"): os.getenv(f"APP_PASS{i}") for i in range(1, 10) if os.getenv(f"APP_USER{i}")}


def require_login():
    if st.session_state.get("user"):
        return
    st.title("Supplier Risk & Discovery Radar")
    st.caption("External supply-chain intelligence for retail sourcing agents · powered by Exa")
    with st.form("login", width=420):
        user = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            expected = accounts().get(user)
            if expected and hmac.compare_digest(password.encode(), expected.encode()):
                st.session_state.user = user
                st.rerun()
            st.error("Invalid username or password.")
    st.stop()


def logout_button():
    st.caption(f"Signed in as {st.session_state.user}")
    if st.button("Sign out"):
        st.session_state.clear()
        st.rerun()
