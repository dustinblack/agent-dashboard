#!/usr/bin/env python3
"""
Test script for PTY terminal size configuration.

This script demonstrates how to set the initial terminal size (rows and columns)
for a PTY before executing a command. This is important because some CLI tools
(like 'ora' spinners used by gemini-cli and claude-code) cache the terminal width
at startup and use it for text wrapping calculations.

Usage:
    python3 test_pty.py

Expected output: Should print "40 150" indicating the terminal was successfully
configured to 40 rows and 150 columns.

This technique is used in the Host Daemon to set a large default terminal width
(200 columns) before spawning AI agents, preventing premature text wrapping
in spinner animations and progress indicators.
"""
import pty
import os
import sys
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
