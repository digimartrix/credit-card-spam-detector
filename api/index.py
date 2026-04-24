"""
Vercel serverless entry point for the EXPayshield Flask application.

Vercel's @vercel/python runtime looks for an `app` variable in this module
that implements the WSGI interface (e.g. a Flask app instance).
"""

import sys
import os

# Ensure the project root is on the Python path so that
# `from backend.app import app` works inside the serverless function.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app import app

# Vercel picks up this `app` variable automatically
