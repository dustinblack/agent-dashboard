#!/usr/bin/env python3
"""
Test script for PTY carriage return handling.

This script demonstrates how Python's pty module handles carriage return (\r)
sequences when a child process uses them to overwrite lines (common in spinner
animations and progress bars).

Expected output: The child process writes multiple lines using \r to overwrite
the same line. The parent should receive all \r characters intact, which can
then be properly rendered by terminal emulators like xterm.js.

Usage:
    python3 test_spinner.py

The output should show the raw string with \r characters preserved, demonstrating
that the PTY correctly transmits line replacement sequences.
"""
import pty
import os
import sys
import time

pid, fd = pty.fork()
if pid == 0:
    # Child process: Simulate a spinner animation
    for i in range(5):
        sys.stdout.write(f"\rSpinner {i}")
        sys.stdout.flush()
        time.sleep(0.1)
    os._exit(0)
else:
    # Parent process: Read all output from child
    output = ""
    while True:
        try:
            data = os.read(fd, 1024)
            if not data:
                break
            output += data.decode()
        except OSError:
            break
    print(repr(output))
