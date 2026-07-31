# wsgi.py - PythonAnywhere entry point
# ASGI to WSGI bridge for FastAPI

import os
import sys

# Add project root to path
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.insert(0, path)

from web_app.main import app as application

# For PythonAnywhere ASGI support
# In PythonAnywhere web tab, set:
#   Working directory: /home/yourusername/accounting_ai_bot
#   ASGI app: wsgi.application
