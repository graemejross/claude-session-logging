#!/usr/bin/env python3
"""
Claude Session Log Server

Simple web server to browse and view Claude session logs over Tailscale.
Serves from ~/claude-logs/ with on-demand HTML conversion.
"""

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Flask, Response, abort

app = Flask(__name__)

LOG_DIR = Path.home() / "claude-logs"
CLEAN_SCRIPT = Path.home() / "claude-log-clean.py"

# Cache for converted HTML (in-memory, cleared on restart)
html_cache = {}


def parse_log_filename(filename):
    """Extract session name and timestamp from log filename."""
    # Format: {session_name}_{YYYYMMDD_HHMMSS}.log
    match = re.match(r'^(.+)_(\d{8}_\d{6})\.log$', filename)
    if match:
        name = match.group(1).replace('_', ' ').title()
        timestamp_str = match.group(2)
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
            return name, timestamp
        except ValueError:
            pass
    return filename, None


def get_sessions():
    """Get list of sessions grouped by name with their logs."""
    sessions = {}

    if not LOG_DIR.exists():
        return sessions

    for logfile in LOG_DIR.glob("*.log"):
        name, timestamp = parse_log_filename(logfile.name)
        size = logfile.stat().st_size

        if name not in sessions:
            sessions[name] = []

        sessions[name].append({
            'filename': logfile.name,
            'timestamp': timestamp,
            'size': size,
            'size_human': format_size(size),
        })

    # Sort logs within each session by timestamp (newest first)
    for name in sessions:
        sessions[name].sort(key=lambda x: x['timestamp'] or datetime.min, reverse=True)

    return sessions


def format_size(size):
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == 'B' else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def convert_log_to_html(logfile):
    """Convert log to HTML, preferring fresh pre-converted files."""
    log_path = LOG_DIR / logfile
    html_path = LOG_DIR / logfile.replace('.log', '.html')

    if not log_path.exists():
        return None

    # Check for pre-converted HTML file (for captured scrollback sessions)
    # Only use if HTML is newer than log (i.e., generated after log was finalized)
    if html_path.exists():
        html_mtime = html_path.stat().st_mtime
        log_mtime = log_path.stat().st_mtime
        if html_mtime >= log_mtime:
            return html_path.read_text()

    # Check cache
    mtime = log_path.stat().st_mtime
    cache_key = f"{logfile}:{mtime}"

    if cache_key in html_cache:
        return html_cache[cache_key]

    # Convert using the clean script (for typescript logs)
    try:
        result = subprocess.run(
            ['python3', str(CLEAN_SCRIPT), str(log_path), '--html'],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            html = result.stdout
            html_cache[cache_key] = html
            return html
    except Exception as e:
        return f"<html><body><pre>Error converting log: {e}</pre></body></html>"

    return None


@app.route('/')
def index():
    """Index page showing all sessions."""
    sessions = get_sessions()

    # Sort sessions by most recent log
    sorted_sessions = sorted(
        sessions.items(),
        key=lambda x: max((log['timestamp'] or datetime.min for log in x[1]), default=datetime.min),
        reverse=True
    )

    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Claude Session Logs</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #1a1a2e;
            color: #eee;
        }
        h1 {
            color: #00d4aa;
            border-bottom: 2px solid #00d4aa;
            padding-bottom: 10px;
        }
        .session {
            background: #16213e;
            border-radius: 8px;
            padding: 15px 20px;
            margin: 15px 0;
        }
        .session h2 {
            margin: 0 0 10px 0;
            color: #00d4aa;
            font-size: 1.2em;
        }
        .session-meta {
            color: #888;
            font-size: 0.9em;
            margin-bottom: 10px;
        }
        .log-list {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        .log-list li {
            padding: 8px 0;
            border-top: 1px solid #2a2a4a;
        }
        .log-list li:first-child {
            border-top: none;
        }
        .log-list a {
            color: #7dd3fc;
            text-decoration: none;
        }
        .log-list a:hover {
            text-decoration: underline;
        }
        .log-meta {
            color: #888;
            font-size: 0.85em;
            margin-left: 10px;
        }
        .empty {
            color: #888;
            font-style: italic;
        }
    </style>
</head>
<body>
    <h1>Claude Session Logs</h1>
"""

    if not sorted_sessions:
        html += '<p class="empty">No session logs found.</p>'
    else:
        for name, logs in sorted_sessions:
            latest = logs[0]['timestamp']
            latest_str = latest.strftime('%Y-%m-%d %H:%M') if latest else 'Unknown'

            html += f'''
    <div class="session">
        <h2>{name}</h2>
        <div class="session-meta">{len(logs)} log(s) &bull; Latest: {latest_str}</div>
        <ul class="log-list">
'''
            for log in logs[:10]:  # Show max 10 per session
                ts = log['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if log['timestamp'] else 'Unknown'
                html += f'''            <li>
                <a href="/log/{log['filename']}">{ts}</a>
                <span class="log-meta">{log['size_human']}</span>
            </li>
'''

            if len(logs) > 10:
                html += f'            <li class="log-meta">... and {len(logs) - 10} more</li>\n'

            html += '        </ul>\n    </div>\n'

    html += """</body>
</html>"""

    return html


@app.route('/log/<filename>')
def view_log(filename):
    """View a specific log file as clean HTML."""
    # Security: ensure filename is safe
    if '/' in filename or '..' in filename:
        abort(400)

    if not filename.endswith('.log'):
        abort(400)

    html = convert_log_to_html(filename)

    if html is None:
        abort(404)

    return Response(html, mimetype='text/html')


@app.route('/raw/<filename>')
def raw_log(filename):
    """View raw log file."""
    if '/' in filename or '..' in filename:
        abort(400)

    log_path = LOG_DIR / filename

    if not log_path.exists():
        abort(404)

    return Response(log_path.read_text(errors='replace'), mimetype='text/plain')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Claude Session Log Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8090, help='Port to listen on')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    print(f"Starting Claude Log Server on http://{args.host}:{args.port}")
    print(f"Log directory: {LOG_DIR}")

    app.run(host=args.host, port=args.port, debug=args.debug)
