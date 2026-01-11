from flask import Flask, render_template, jsonify
import threading
import logging

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# In-Memory State (Shared with Telegram Bot via specialized link or file)
# For MVP, we'll read the same Log Files
from routine_manager import routine_db
from metro_data import METRO_GRAPH

@app.route('/')
def home():
    return "Jarvis Visual Cortex Online."

@app.route('/dashboard')
def dashboard():
    """
    Renders the Personal Dashboard.
    Shows: Current Routine, Metro Status, Quick Actions.
    """
    routines = routine_db.get_routines()
    return render_template('dashboard.html', routines=routines, station_count=len(METRO_GRAPH["stations"]))

import os

def run_server():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def start_visual_cortex():
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()
