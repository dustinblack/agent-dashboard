#!/usr/bin/env python3
"""
Test script for PTY terminal size configuration.

This script demonstrates how to set and verify the terminal size for a PTY.
Correct terminal size is critical because CLI tools use it to calculate
line wrapping — if the PTY width doesn't match the actual display width,
cursor-up escape sequences will target wrong positions, causing visual
artifacts like repeated lines.

Usage:
    python3 test_pty.py

Expected output: Should print "40 150" indicating the terminal was successfully
configured to 40 rows and 150 columns.
"""
import pty
import os
import struct
import fcntl
import termios

pid, fd = pty.fork()
if pid == 0:
    # Child process: Set terminal size and verify it
    size = struct.pack('HHHH', 40, 150, 0, 0)
    fcntl.ioctl(0, termios.TIOCSWINSZ, size)
    os.execvpe('stty', ['stty', 'size'], os.environ)
else:
    # Parent process: Read the output from stty
    print(os.read(fd, 1024).decode())
