#!/usr/bin/env python3
"""
Test script for PTY spinner rendering with cursor movement escape sequences.

This script simulates how CLI tools like gemini-cli render spinner animations
using ANSI escape sequences. It demonstrates the cursor-up + erase-line
pattern used by 'ink'-based Node.js CLIs to overwrite previous renders.

The key insight: the PTY read buffer must be large enough to capture a
complete render frame in a single read. If a frame is split across multiple
reads (and thus multiple term.write() calls in xterm.js), the split escape
sequences can cause rendering artifacts like repeated lines.

Usage:
    python3 test_spinner.py

Expected output: Raw bytes showing escape sequences like:
  \\x1b[2K  - Erase entire line
  \\x1b[1A  - Cursor up one row
  \\x1b[G   - Cursor to column 1
  \\r       - Carriage return
"""
import pty
import os
import sys
import time

SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

pid, fd = pty.fork()
if pid == 0:
    # Child process: Simulate an ink-style multi-line render with cursor-up
    env = os.environ.copy()
    env['TERM'] = 'xterm-256color'

    for i in range(5):
        if i > 0:
            # Erase previous render (2 lines): erase + up, erase + go to col 1
            sys.stdout.write('\x1b[2K\x1b[1A\x1b[2K\x1b[G')
        # Write 2-line render: spinner + status
        sys.stdout.write(f' {SPINNER_FRAMES[i]} Loading... ({i}s)\r\n')
        sys.stdout.write(f' Status: processing\r\n')
        sys.stdout.flush()
        time.sleep(0.2)
    os._exit(0)
else:
    # Parent process: Read output and display raw bytes
    output = b''
    while True:
        try:
            data = os.read(fd, 65536)
            if not data:
                break
            output += data
        except OSError:
            break
    print(f"Total bytes: {len(output)}")
    print(f"Raw: {output!r}")
