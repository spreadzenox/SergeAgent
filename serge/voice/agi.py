#!/usr/bin/env python3
"""Asterisk AGI protocol: commands over stdin/stdout. Hangup-safe."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


class AgiHangup(Exception):
    pass


class Agi:
    def __init__(self, stdin: Any = None, stdout: Any = None):
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.env: dict[str, str] = {}
        while True:
            line = self.stdin.readline()
            if not line or line.strip() == '':
                break
            if ':' in line:
                key, _, value = line.partition(':')
                self.env[key.strip()] = value.strip()

    def command(self, text: str) -> str:
        try:
            self.stdout.write(text + '\n')
            self.stdout.flush()
            line = self.stdin.readline()
        except (BrokenPipeError, OSError):
            raise AgiHangup()
        if not line:
            raise AgiHangup()
        line = line.strip()
        if line.startswith('200 result=-1'):
            raise AgiHangup()
        if not line.startswith('200 result='):
            raise AgiHangup()
        return line[len('200 result=') :].strip()

    def verbose(self, message: str) -> None:
        safe = message.replace('"', "'")[:400]
        try:
            self.command(f'VERBOSE "{safe}" 1')
        except AgiHangup:
            raise

    def answer(self) -> None:
        self.command('ANSWER')

    def stream(self, path_no_ext: str) -> str:
        return self.command(f'STREAM FILE "{path_no_ext}" ""')

    def get_data(
        self, path_no_ext: str, timeout_ms: int, max_digits: int = 1
    ) -> str:
        raw = self.command(
            f'GET DATA "{path_no_ext}" {timeout_ms} {max_digits}'
        )
        digits = raw.split()[0] if raw else ''
        if digits.startswith('(') and digits.endswith(')'):
            digits = digits[1:-1]
        return '' if digits in {'0', '-1', ''} else digits

    def record(
        self, path_no_ext: str, timeout_ms: int, silence_s: int = 0
    ) -> None:
        self.command(
            f'RECORD FILE "{path_no_ext}" wav "#" {timeout_ms} {silence_s}'
            if silence_s
            else f'RECORD FILE "{path_no_ext}" wav "#" {timeout_ms}'
        )

    def hangup(self) -> None:
        try:
            self.command('HANGUP')
        except AgiHangup:
            pass


def strip_ext(path: Path) -> str:
    return str(path.with_suffix(''))
