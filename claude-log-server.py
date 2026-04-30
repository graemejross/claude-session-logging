#!/usr/bin/env python3
"""
Claude Session Log Server

Web server to browse and view Claude session logs over Tailscale.
Serves from ~/claude-logs/ with on-demand HTML conversion.

Features:
  - Live session indicators (green LIVE badge)
  - Auto-refresh for active sessions (10s)
  - Full-text search across raw logs
  - Old log compression (gzip after 7 days)
  - Serves both .log and .log.gz files
"""

import gzip
import os
import re
import subprocess
import time
from datetime import datetime
from html import escape
from pathlib import Path
from flask import Flask, Response, abort, request

app = Flask(__name__)

LOG_DIR = Path.home() / "claude-logs"
CLEAN_SCRIPT = Path.home() / "claude-log-clean.py"

# Cache for converted HTML (in-memory, cleared on restart)
html_cache = {}


def parse_log_filename(filename):
    """Extract session name and timestamp from log filename.

    Handles both .log and .log.gz files.
    """
    # Strip .gz suffix for parsing
    base = filename
    if base.endswith(".gz"):
        base = base[:-3]

    # Format: {session_name}_{YYYYMMDD_HHMMSS}.log
    match = re.match(r"^(.+)_(\d{8}_\d{6})\.log$", base)
    if match:
        name = match.group(1).replace("_", " ").title()
        timestamp_str = match.group(2)
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            return name, timestamp
        except ValueError:
            pass
    return filename, None


def is_session_active(logfile_name):
    """Check if a session has an active streaming converter."""
    # Strip .gz - compressed logs can't be active
    if logfile_name.endswith(".gz"):
        return False

    pid_file = LOG_DIR / (logfile_name + ".converter-pid")
    if not pid_file.exists():
        return False

    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)  # Check if process exists
        return True
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        return False


def html_age(logfile_name):
    """Get age of the HTML file for a log, if it exists."""
    base = logfile_name
    if base.endswith(".gz"):
        base = base[:-3]
    html_path = LOG_DIR / base.replace(".log", ".html")
    if html_path.exists():
        age_secs = time.time() - html_path.stat().st_mtime
        if age_secs < 60:
            return f"{int(age_secs)}s ago"
        elif age_secs < 3600:
            return f"{int(age_secs / 60)}m ago"
        elif age_secs < 86400:
            return f"{int(age_secs / 3600)}h ago"
        else:
            return f"{int(age_secs / 86400)}d ago"
    return None


def get_sessions():
    """Get list of sessions grouped by name with their logs."""
    sessions = {}

    if not LOG_DIR.exists():
        return sessions

    # Collect both .log and .log.gz files
    for pattern in ["*.log", "*.log.gz"]:
        for logfile in LOG_DIR.glob(pattern):
            name, timestamp = parse_log_filename(logfile.name)
            size = logfile.stat().st_size
            active = is_session_active(logfile.name)
            age = html_age(logfile.name)
            compressed = logfile.name.endswith(".gz")

            if name not in sessions:
                sessions[name] = []

            sessions[name].append(
                {
                    "filename": logfile.name,
                    "timestamp": timestamp,
                    "size": size,
                    "size_human": format_size(size),
                    "active": active,
                    "html_age": age,
                    "compressed": compressed,
                }
            )

    # Sort logs within each session by timestamp (newest first)
    for name in sessions:
        sessions[name].sort(key=lambda x: x["timestamp"] or datetime.min, reverse=True)

    return sessions


def format_size(size):
    """Format file size in human readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def read_log_content(logfile):
    """Read log file content, handling both plain and gzipped files."""
    log_path = LOG_DIR / logfile
    if not log_path.exists():
        return None

    if logfile.endswith(".gz"):
        with gzip.open(log_path, "rt", errors="replace") as f:
            return f.read()
    else:
        return log_path.read_text(errors="replace")


def convert_log_to_html(logfile):
    """Convert log to HTML, preferring fresh pre-converted files."""
    # Determine the base log name (without .gz)
    base_logfile = logfile
    if base_logfile.endswith(".gz"):
        base_logfile = base_logfile[:-3]

    log_path = LOG_DIR / logfile
    html_path = LOG_DIR / base_logfile.replace(".log", ".html")

    if not log_path.exists():
        return None

    # Check for pre-converted HTML file
    # For active sessions, always use the streaming HTML (even if slightly stale)
    if html_path.exists():
        if is_session_active(base_logfile):
            return html_path.read_text()
        html_mtime = html_path.stat().st_mtime
        log_mtime = log_path.stat().st_mtime
        if html_mtime >= log_mtime:
            return html_path.read_text()

    # Check cache
    mtime = log_path.stat().st_mtime
    cache_key = f"{logfile}:{mtime}"

    if cache_key in html_cache:
        return html_cache[cache_key]

    # For compressed files, decompress to temp then convert
    if logfile.endswith(".gz"):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as tmp:
            tmp_path = tmp.name
            with gzip.open(log_path, "rb") as gz:
                tmp.write(gz.read())
        try:
            result = subprocess.run(
                ["python3", str(CLEAN_SCRIPT), tmp_path, "--html"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                html = result.stdout
                html_cache[cache_key] = html
                return html
        except Exception as e:
            return f"<html><body><pre>Error converting log: {e}</pre></body></html>"
        finally:
            os.unlink(tmp_path)
        return None

    # Convert using the clean script (for typescript logs)
    try:
        result = subprocess.run(
            ["python3", str(CLEAN_SCRIPT), str(log_path), "--html"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            html = result.stdout
            html_cache[cache_key] = html
            return html
    except Exception as e:
        return f"<html><body><pre>Error converting log: {e}</pre></body></html>"

    return None


def inject_auto_refresh(html_content):
    """Inject auto-refresh meta tag into HTML for live sessions."""
    refresh_tag = '<meta http-equiv="refresh" content="10">'
    # Insert after <head> or <meta charset>
    if "<head>" in html_content:
        html_content = html_content.replace("<head>", f"<head>\n{refresh_tag}", 1)
    elif "<HEAD>" in html_content:
        html_content = html_content.replace("<HEAD>", f"<HEAD>\n{refresh_tag}", 1)
    return html_content


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Index page showing all sessions with search and live indicators."""
    sessions = get_sessions()

    # Sort sessions by most recent log
    sorted_sessions = sorted(
        sessions.items(),
        key=lambda x: max(
            (log["timestamp"] or datetime.min for log in x[1]), default=datetime.min
        ),
        reverse=True,
    )

    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Clarence Session Logs</title>
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
        .search-box {
            margin: 15px 0;
            display: flex;
            gap: 10px;
        }
        .search-box input[type="text"] {
            flex: 1;
            padding: 10px 14px;
            border: 1px solid #2a2a4a;
            border-radius: 6px;
            background: #16213e;
            color: #eee;
            font-size: 14px;
        }
        .search-box input[type="text"]::placeholder {
            color: #666;
        }
        .search-box button {
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            background: #00d4aa;
            color: #1a1a2e;
            font-weight: bold;
            cursor: pointer;
        }
        .search-box button:hover {
            background: #00b894;
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
            display: flex;
            align-items: center;
            gap: 10px;
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
        }
        .badge-live {
            display: inline-block;
            background: #00d4aa;
            color: #1a1a2e;
            font-size: 0.7em;
            font-weight: bold;
            padding: 2px 6px;
            border-radius: 4px;
            letter-spacing: 0.5px;
            animation: pulse 2s ease-in-out infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
        .badge-gz {
            display: inline-block;
            background: #555;
            color: #ccc;
            font-size: 0.65em;
            padding: 1px 4px;
            border-radius: 3px;
        }
        .html-age {
            color: #666;
            font-size: 0.8em;
        }
        .empty {
            color: #888;
            font-style: italic;
        }
    </style>
</head>
<body>
    <h1>Clarence Session Logs</h1>

    <form class="search-box" action="/search" method="get">
        <input type="text" name="q" placeholder="Search logs..." autocomplete="off">
        <button type="submit">Search</button>
    </form>
"""

    if not sorted_sessions:
        html += '<p class="empty">No session logs found.</p>'
    else:
        for name, logs in sorted_sessions:
            latest = logs[0]["timestamp"]
            latest_str = latest.strftime("%Y-%m-%d %H:%M") if latest else "Unknown"
            has_active = any(log["active"] for log in logs)

            session_badge = ""
            if has_active:
                session_badge = ' <span class="badge-live">LIVE</span>'

            html += f"""
    <div class="session">
        <h2>{escape(name)}{session_badge}</h2>
        <div class="session-meta">{len(logs)} log(s) &bull; Latest: {latest_str}</div>
        <ul class="log-list">
"""
            for log in logs[:10]:  # Show max 10 per session
                ts = (
                    log["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
                    if log["timestamp"]
                    else "Unknown"
                )
                badges = ""
                if log["active"]:
                    badges += ' <span class="badge-live">LIVE</span>'
                if log["compressed"]:
                    badges += ' <span class="badge-gz">gz</span>'
                age_str = ""
                if log["html_age"] and log["active"]:
                    age_str = (
                        f' <span class="html-age">updated {log["html_age"]}</span>'
                    )

                html += f"""            <li>
                <a href="/log/{escape(log["filename"])}">{ts}</a>
                <span class="log-meta">{log["size_human"]}</span>{badges}{age_str}
            </li>
"""

            if len(logs) > 10:
                html += f'            <li class="log-meta">... and {len(logs) - 10} more</li>\n'

            html += "        </ul>\n    </div>\n"

    html += """</body>
</html>"""

    return html


@app.route("/log/<filename>")
def view_log(filename):
    """View a specific log file as clean HTML."""
    # Security: ensure filename is safe
    if "/" in filename or ".." in filename:
        abort(400)

    if not (filename.endswith(".log") or filename.endswith(".log.gz")):
        abort(400)

    html = convert_log_to_html(filename)

    if html is None:
        abort(404)

    # For active sessions, inject auto-refresh
    base = filename[:-3] if filename.endswith(".gz") else filename
    if is_session_active(base):
        html = inject_auto_refresh(html)

    return Response(html, mimetype="text/html")


@app.route("/raw/<filename>")
def raw_log(filename):
    """View raw log file."""
    if "/" in filename or ".." in filename:
        abort(400)

    content = read_log_content(filename)
    if content is None:
        abort(404)

    return Response(content, mimetype="text/plain")


@app.route("/search")
def search():
    """Search across raw log files."""
    query = request.args.get("q", "").strip()

    if not query:
        return Response("Missing search query", status=400)

    # Security: limit query length
    if len(query) > 200:
        return Response("Query too long", status=400)

    results = []
    max_results = 100
    count = 0

    if LOG_DIR.exists():
        # Search .log files (plain text)
        for logfile in sorted(
            LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            if count >= max_results:
                break
            try:
                result = subprocess.run(
                    ["grep", "-i", "-n", "-C", "1", "--", query, str(logfile)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    matches = result.stdout.strip().split("\n")
                    results.append(
                        {
                            "filename": logfile.name,
                            "matches": matches[:20],  # Limit matches per file
                        }
                    )
                    count += len(matches[:20])
            except (subprocess.TimeoutExpired, Exception):
                continue

        # Search .log.gz files
        for logfile in sorted(
            LOG_DIR.glob("*.log.gz"), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            if count >= max_results:
                break
            try:
                result = subprocess.run(
                    ["zgrep", "-i", "-n", "-C", "1", "--", query, str(logfile)],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0 and result.stdout.strip():
                    matches = result.stdout.strip().split("\n")
                    results.append(
                        {
                            "filename": logfile.name,
                            "matches": matches[:20],
                        }
                    )
                    count += len(matches[:20])
            except (subprocess.TimeoutExpired, Exception):
                continue

    # Build results page
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Search: {escape(query)} - Clarence Logs</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #1a1a2e;
            color: #eee;
        }}
        h1 {{
            color: #00d4aa;
            border-bottom: 2px solid #00d4aa;
            padding-bottom: 10px;
        }}
        .search-box {{
            margin: 15px 0;
            display: flex;
            gap: 10px;
        }}
        .search-box input[type="text"] {{
            flex: 1;
            padding: 10px 14px;
            border: 1px solid #2a2a4a;
            border-radius: 6px;
            background: #16213e;
            color: #eee;
            font-size: 14px;
        }}
        .search-box button {{
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            background: #00d4aa;
            color: #1a1a2e;
            font-weight: bold;
            cursor: pointer;
        }}
        a {{ color: #7dd3fc; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .result {{
            background: #16213e;
            border-radius: 8px;
            padding: 15px 20px;
            margin: 15px 0;
        }}
        .result h3 {{
            margin: 0 0 10px 0;
            color: #00d4aa;
            font-size: 1em;
        }}
        .result pre {{
            font-family: 'Fira Code', 'Consolas', monospace;
            font-size: 12px;
            color: #aaa;
            white-space: pre-wrap;
            word-wrap: break-word;
            margin: 0;
            max-height: 300px;
            overflow-y: auto;
        }}
        .back-link {{
            margin-bottom: 15px;
            display: inline-block;
        }}
        .count {{
            color: #888;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <a class="back-link" href="/">&larr; Back to index</a>
    <h1>Search Results</h1>

    <form class="search-box" action="/search" method="get">
        <input type="text" name="q" value="{escape(query)}" autocomplete="off">
        <button type="submit">Search</button>
    </form>

    <p class="count">Found matches in {len(results)} file(s) ({count} lines)</p>
"""

    if not results:
        html += f'<p style="color:#888;">No matches for "{escape(query)}".</p>'
    else:
        for r in results:
            html += f"""    <div class="result">
        <h3><a href="/log/{escape(r["filename"])}">{escape(r["filename"])}</a></h3>
        <pre>{escape(chr(10).join(r["matches"]))}</pre>
    </div>
"""

    html += """</body>
</html>"""

    return html


@app.route("/compress")
def compress_old_logs():
    """Compress log and HTML files older than 7 days.

    GET /compress?dry_run=1  - preview what would be compressed
    GET /compress             - actually compress
    """
    dry_run = request.args.get("dry_run", "0") == "1"
    cutoff = time.time() - (7 * 86400)
    compressed = []
    skipped = []

    if LOG_DIR.exists():
        for logfile in sorted(LOG_DIR.glob("*.log")):
            if logfile.stat().st_mtime > cutoff:
                continue

            # Skip if session is active
            if is_session_active(logfile.name):
                skipped.append(f"{logfile.name} (active session)")
                continue

            if dry_run:
                compressed.append(logfile.name)
            else:
                try:
                    # Compress the log file
                    subprocess.run(["gzip", str(logfile)], check=True, timeout=60)
                    compressed.append(logfile.name)

                    # Compress matching HTML file too
                    html_file = logfile.with_suffix(".html")
                    if html_file.exists() and html_file.stat().st_mtime < cutoff:
                        subprocess.run(["gzip", str(html_file)], check=True, timeout=60)
                        compressed.append(html_file.name)
                except Exception as e:
                    skipped.append(f"{logfile.name} (error: {e})")

    action = "Would compress" if dry_run else "Compressed"
    result = f"{action} {len(compressed)} file(s):\n"
    for f in compressed:
        result += f"  {f}\n"
    if skipped:
        result += f"\nSkipped {len(skipped)} file(s):\n"
        for s in skipped:
            result += f"  {s}\n"

    return Response(result, mimetype="text/plain")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Claude Session Log Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8090, help="Port to listen on")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    print(f"Starting Claude Log Server on http://{args.host}:{args.port}")
    print(f"Log directory: {LOG_DIR}")

    app.run(host=args.host, port=args.port, debug=args.debug)
