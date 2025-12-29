#!/usr/bin/env python3
"""
Clean claude session logs by simulating terminal playback.
Removes keystroke-by-keystroke capture and shows final rendered output.
"""

import sys
import pyte

# ANSI color to CSS color mapping
COLORS = {
    'black': '#000000',
    'red': '#cc0000',
    'green': '#4e9a06',
    'brown': '#c4a000',
    'yellow': '#c4a000',
    'blue': '#3465a4',
    'magenta': '#75507b',
    'cyan': '#06989a',
    'white': '#d3d7cf',
    'default': '#d3d7cf',
    # Bright variants
    'brightblack': '#555753',
    'brightred': '#ef2929',
    'brightgreen': '#8ae234',
    'brightyellow': '#fce94f',
    'brightblue': '#729fcf',
    'brightmagenta': '#ad7fa8',
    'brightcyan': '#34e2e2',
    'brightwhite': '#eeeeec',
}

def char_to_html(char):
    """Convert a pyte Char to HTML with styling."""
    if char.data == ' ' and char.fg == 'default' and char.bg == 'default':
        return ' '

    styles = []

    # Foreground color
    fg = char.fg
    if fg and fg != 'default':
        if isinstance(fg, str):
            color = COLORS.get(fg, COLORS.get('bright' + fg, '#d3d7cf'))
        else:
            # 256-color or RGB
            color = f'#{fg:06x}' if isinstance(fg, int) else '#d3d7cf'
        styles.append(f'color:{color}')

    # Background color
    bg = char.bg
    if bg and bg != 'default':
        if isinstance(bg, str):
            color = COLORS.get(bg, COLORS.get('bright' + bg, '#000000'))
        else:
            color = f'#{bg:06x}' if isinstance(bg, int) else '#000000'
        styles.append(f'background-color:{color}')

    # Bold
    if char.bold:
        styles.append('font-weight:bold')

    # Escape HTML
    data = char.data
    if data == '<':
        data = '&lt;'
    elif data == '>':
        data = '&gt;'
    elif data == '&':
        data = '&amp;'

    if styles:
        return f'<span style="{";".join(styles)}">{data}</span>'
    return data


def screen_to_html(screen):
    """Convert pyte screen to HTML with colors."""
    lines = []

    for y in range(screen.lines):
        line_html = []
        line = screen.buffer[y]

        # Find last non-empty character
        last_char = 0
        for x in range(screen.columns):
            if line[x].data != ' ' or line[x].bg != 'default':
                last_char = x

        # Only process up to last non-empty char
        for x in range(last_char + 1):
            char = line[x]
            line_html.append(char_to_html(char))

        line_str = ''.join(line_html).rstrip()
        if line_str:
            lines.append(line_str)

    # Remove trailing empty lines
    while lines and not lines[-1].strip():
        lines.pop()

    return '\n'.join(lines)


def clean_log(input_file, output_file=None, html=False):
    """Process a script typescript file and output clean text or HTML."""

    # Read the raw log
    with open(input_file, 'rb') as f:
        data = f.read()

    # Create terminal emulator
    screen = pyte.Screen(200, 10000)
    stream = pyte.Stream(screen)

    # Skip the "Script started" header line
    try:
        first_newline = data.index(b'\n')
        data = data[first_newline + 1:]
    except ValueError:
        pass

    # Feed data to terminal emulator
    try:
        stream.feed(data.decode('utf-8', errors='replace'))
    except Exception as e:
        print(f"Warning: {e}", file=sys.stderr)

    if html:
        content = screen_to_html(screen)
        output = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Claude Session Log</title>
<style>
body {{
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
    font-size: 14px;
    padding: 20px;
    margin: 0;
}}
pre {{
    white-space: pre-wrap;
    word-wrap: break-word;
    margin: 0;
    line-height: 1.4;
}}
</style>
</head>
<body>
<pre>{content}</pre>
</body>
</html>'''
    else:
        # Plain text output
        lines = []
        for line in screen.display:
            stripped = line.rstrip()
            if stripped:
                lines.append(stripped)
        while lines and not lines[-1].strip():
            lines.pop()
        output = '\n'.join(lines)

    if output_file:
        with open(output_file, 'w') as f:
            f.write(output)
        print(f"Written to: {output_file}")
    else:
        print(output)

    return output


def main():
    if len(sys.argv) < 2:
        print("Usage: claude-log-clean.py <logfile> [output] [--html]")
        print("       Cleans typescript logs by simulating terminal playback")
        print("       --html: Generate HTML with colors (auto if output ends in .html)")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = None
    html = False

    for arg in sys.argv[2:]:
        if arg == '--html':
            html = True
        else:
            output_file = arg

    # Auto-detect HTML from output filename
    if output_file and output_file.endswith('.html'):
        html = True

    clean_log(input_file, output_file, html)


if __name__ == '__main__':
    main()
