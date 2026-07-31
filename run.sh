#!/usr/bin/env bash
if [ -d "venv" ]; then
    source venv/bin/activate
fi
streamlit run src/app.py