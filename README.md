# Claude Session Logging

A complete session logging solution for [Claude Code](https://claude.ai/code), capturing terminal sessions with TMUX and converting them to clean, readable HTML with preserved colors.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
  - [Starting a Session](#starting-a-session)
  - [Listing Sessions](#listing-sessions)
  - [Converting to HTML](#converting-to-html)
- [Commands Reference](#commands-reference)
- [How It Works](#how-it-works)
- [File Locations](#file-locations)
- [Troubleshooting](#troubleshooting)

## Features

- **Automatic session capture** - Records all terminal I/O using `script`
- **TMUX integration** - Sessions persist even if your SSH connection drops
- **Clean HTML export** - Removes keystroke-by-keystroke noise using terminal emulation
- **Color preservation** - HTML output maintains terminal colors and formatting
- **90% size reduction** - Clean logs are ~10% the size of raw captures
- **Simple aliases** - `cs` to start, `claude-logs` to list, `claude-log-html` to convert

## Installation

### Prerequisites

```bash
# Install required packages
sudo apt-get install tmux

# Install Python dependency
pip3 install pyte
```

### Setup

1. Clone the repository:
```bash
git clone https://github.com/graemejross/claude-session-logging.git ~/claude-session-logging
```

2. Make scripts executable:
```bash
chmod +x ~/claude-session-logging/claude-session
chmod +x ~/claude-session-logging/claude-log-clean.py
```

3. Create symlinks (optional):
```bash
ln -s ~/claude-session-logging/claude-session ~/claude-session
ln -s ~/claude-session-logging/claude-log-clean.py ~/claude-log-clean.py
```

4. Add aliases to your `~/.bash_aliases` or `~/.bashrc`:
```bash
# Claude session logging
alias cs='~/claude-session'
alias claude-logs='~/claude-session --list'

# Convert logs to clean HTML
claude-log-html() {
    if [ -z "$1" ]; then
        echo "Usage: claude-log-html <logfile> [output.html]"
        return 1
    fi
    local input="$1"
    local output="${2:-${input%.log}.html}"
    python3 ~/claude-log-clean.py "$input" "$output"
}
```

5. Create logs directory:
```bash
mkdir -p ~/claude-logs
```

6. Reload your shell:
```bash
source ~/.bashrc
```

## Quick Start

```bash
# Start a logged Claude session
cs "my project"

# ... work with Claude ...
# (Exit with Ctrl-D or type 'exit')

# View your sessions
claude-logs

# Convert to shareable HTML
claude-log-html ~/claude-logs/my_project_20251229_103000.log
```

## Usage

### Starting a Session

**With a name:**
```bash
cs "bug investigation"
```

**Interactive (prompts for name):**
```bash
cs
```

The session name is sanitized for use as a filename:
- Converted to lowercase
- Spaces become underscores
- Special characters removed

**Output:**
```
Starting Claude session: bug investigation
Log file: /home/user/claude-logs/bug_investigation_20251229_103000.log
```

### Listing Sessions

View recent sessions with sizes and dates:

```bash
claude-logs
```

**Output:**
```
Recent Claude sessions:

SESSION                                        SIZE  DATE
bug_investigation                              45K   2025-12-29 10:30:00
feature_planning                               128K  2025-12-28 14:15:00
code_review                                    89K   2025-12-28 09:00:00
```

### Converting to HTML

**Basic conversion:**
```bash
claude-log-html ~/claude-logs/bug_investigation_20251229_103000.log
# Creates: ~/claude-logs/bug_investigation_20251229_103000.html
```

**Specify output file:**
```bash
claude-log-html ~/claude-logs/session.log ~/Desktop/session.html
```

**Using the Python script directly:**
```bash
# Plain text output
python3 ~/claude-log-clean.py session.log session.txt

# HTML with colors
python3 ~/claude-log-clean.py session.log session.html

# Force HTML output
python3 ~/claude-log-clean.py session.log output --html
```

## Commands Reference

| Command | Description |
|---------|-------------|
| `cs [name]` | Start a logged Claude session |
| `cs --list` | List recent sessions |
| `cs --help` | Show help |
| `claude-logs` | Alias for `cs --list` |
| `claude-log-html <log> [out]` | Convert log to clean HTML |

### claude-session Options

```
Usage: claude-session [OPTIONS] [session-name]

Options:
  --list, -l     List recent Claude sessions
  --help, -h     Show this help message

Arguments:
  session-name   Name for the session (optional, will prompt if not provided)
```

### claude-log-clean.py Options

```
Usage: claude-log-clean.py <logfile> [output] [--html]

Arguments:
  logfile    Input typescript log file
  output     Output file (optional, prints to stdout if omitted)
  --html     Force HTML output (auto-detected if output ends in .html)
```

## How It Works

### Session Capture

1. **TMUX wrapper** - `claude-session` creates a TMUX session for persistence
2. **Script recording** - Uses `script -q -f` to capture all terminal I/O in real-time
3. **Raw logs** - Typescript files contain every keystroke and screen update

### Log Cleaning

The raw `script` output includes every keystroke as you type, plus autocomplete suggestions and screen redraws. For example, typing "prompt" appears as:

```
> p
> pr
> pro
> prom
> promp
> prompt
```

The `claude-log-clean.py` script uses the `pyte` terminal emulator to:

1. **Replay the typescript** through a virtual terminal
2. **Render the final state** of each screen update
3. **Generate clean output** showing only what you'd see on screen
4. **Preserve colors** by extracting ANSI color codes per character

**Result:** A 2.2MB raw log becomes a 300KB clean HTML file.

### TMUX Behavior

The script handles two scenarios:

1. **Outside TMUX:** Creates new session `claude-{name}`, then re-invokes itself inside
2. **Inside TMUX:** Starts `script` logging and execs into `claude`

This ensures:
- Sessions persist if your connection drops
- No accidental TMUX nesting
- Ctrl-C passes through to Claude correctly

## File Locations

| Path | Purpose |
|------|---------|
| `~/claude-session` | Main session script |
| `~/claude-log-clean.py` | Log cleaning/HTML conversion |
| `~/claude-logs/` | Log storage directory |
| `~/.bash_aliases` | Shell aliases and functions |

### Log File Format

```
~/claude-logs/{session_name}_{YYYYMMDD_HHMMSS}.log
```

Example: `~/claude-logs/bug_investigation_20251229_103000.log`

## Troubleshooting

### "pyte not found"

Install the Python terminal emulator library:
```bash
pip3 install pyte
```

### Session not logging

Ensure you're running `claude-session` or the `cs` alias, not `claude` directly.

### HTML has no colors

Make sure you're using `claude-log-html` (which uses terminal emulation) rather than converting with `aha` directly.

### TMUX session already exists

If a session with the same name exists:
```bash
tmux kill-session -t claude-myproject
```

### Log file is empty

Check that `script` is installed:
```bash
which script
# Should output: /usr/bin/script
```

## Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `tmux` | Session persistence | `apt install tmux` |
| `script` | Terminal recording | Part of `util-linux` |
| `pyte` | Terminal emulation | `pip3 install pyte` |

## License

MIT License - See [LICENSE](LICENSE) for details.

## Author

Created by Graeme Ross ([@graemejross](https://github.com/graemejross))
