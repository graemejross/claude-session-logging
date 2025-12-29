# Project 16: Claude Logging

**Status:** ✅ Complete
**System:** claude VM
**Created:** 2025-12-29

## Overview

TMUX-based session logging for Claude Code, providing automatic capture of all terminal output to timestamped log files with HTML conversion capability.

## Components

### Main Script: `~/claude-session`

Manages logged Claude Code sessions within TMUX.

**Usage:**
```bash
~/claude-session [session-name]    # Start logged session
~/claude-session --list            # Show recent logs
~/claude-session --help            # Show help
```

**Features:**
- Optional session name argument (prompts if not provided)
- Sanitizes names for filenames (lowercase, underscores, alphanumeric)
- Real-time log flushing with `script -q -f`
- TMUX nesting avoidance (documented in script comments)
- Ctrl-C passes through to Claude

### Log Files

**Location:** `~/claude-logs/`
**Format:** `{session_name}_{YYYYMMDD_HHMMSS}.log`

### HTML Conversion

**Function:** `claude-log-html <logfile> [output.html]`
**Requires:** `aha` (installed)

Converts ANSI terminal logs to styled HTML with black background.

### Aliases (in ~/.bash_aliases)

| Alias | Command |
|-------|---------|
| `cs` | `~/claude-session` |
| `claude-logs` | `~/claude-session --list` |

## TMUX Behaviour

The script handles two scenarios:

1. **Outside TMUX:** Creates new TMUX session named `claude-{name}`, then re-invokes itself inside that session
2. **Inside TMUX:** Starts `script` logging directly and execs into `claude`

This ensures logging always happens inside TMUX for session persistence, while avoiding accidental TMUX nesting.

## Files

| File | Purpose |
|------|---------|
| `~/claude-session` | Main script (executable) |
| `~/claude-logs/` | Log directory |
| `~/.bash_aliases` | Aliases and `claude-log-html` function |

## Dependencies

- `tmux` - Terminal multiplexer
- `script` - Terminal session recording (part of util-linux)
- `aha` - ANSI to HTML converter (installed 2025-12-29)

## Example Session

```bash
# Start a new session
$ cs "bug investigation"
✓ Starting Claude session: bug investigation
▶ Log file: /home/graeme/claude-logs/bug_investigation_20251229_103000.log

# ... work with Claude ...

# Later, view logs
$ claude-logs
Recent Claude sessions:

SESSION                                        SIZE  DATE
bug_investigation                              45K   2025-12-29 10:30:00

# Convert to HTML
$ claude-log-html ~/claude-logs/bug_investigation_20251229_103000.log
Created: /home/graeme/claude-logs/bug_investigation_20251229_103000.html
```

## Changelog

### 2025-12-29
- Initial implementation
- Created `~/claude-session` script
- Added aliases to `~/.bash_aliases`
- Installed `aha` for HTML conversion
- Created `~/claude-logs/` directory
