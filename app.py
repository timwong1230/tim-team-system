import streamlit as st
import pandas as pd
import sqlite3
import datetime
import base64

# --- 1. Page Config ---
st.set_page_config(page_title="TIM TEAM Workspace", page_icon="🦁", layout="wide")
DB_FILE = 'tim_team.db'

# --- 2. CSS ---
st.markdown("""
<style>
    .stApp {background-color: #F8F9FA;}
    [data-testid="stSidebar"] {background-color: #FFFFFF; border-right: 1px solid #E0E0E0;}
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E0E0E0;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    [data-testid="stSidebar"] img {
        border-radius: 50%;
        border: 2px solid #fff;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# --- 3. DB Functions ---
def run_query(query, params=(), fetch=False):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(query, params)
            if fetch: return c.fetchall()
            conn.commit()
    except: return []

def init_db():
    # 使用三引號防止斷行