#!/usr/bin/env python3
"""Turn-based voice call leg (Asterisk AGI entry). Robust fallback path.

Rework target (matrix C, point P5) is speech-to-speech realtime. This
module remains the NPV-compatible floor: when realtime is unavailable
(or fails mid-call) the call degrades here — never a crash, never
silence, never a hard hangup.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from serge.voice.agi import Agi, AgiHangup, strip_ext  # noqa: E402
from serge.voice.ledger import VoiceLedger  # noqa: E402
from serge.voice.policy import default_ledger_path  # noqa: E402
from serge.voice.providers import (  # noqa: E402
    chat_reply,
    config_root,
    secrets,
    synthesize,
    system_root,
    transcribe,
)

MAX_TURNS = 4
RECORD_TIMEOUT_MS = 7000
RECORD_SILENCE_S = 2
VOICEMAIL_TIMEOUT_MS = 45000

INBOUND_GREETING = (
    'Bonjour, vous êtes bien chez Serge. '
    'Je vous écoute, que puis-je pour vous ?'
)
OUTBOUND_DEFAULT_PITCH = (
    'Bonjour, ici Serge. Je vous appelle suite à votre demande.'
)
CALLBACK_MENU = (
    'Pour être rappelé par un humain, tapez 1. '
    'Sinon, laissez votre message après le bip.'
)
NOT_UNDERSTOOD = "Pardon, je n'ai pas compris. Pouvez-vous répéter ?"
CANNOT_HEAR = (
    'Je ne vous entends pas. Laissez votre message après le bip, '
    'nous vous rappellerons.'
)
GOODBYE = 'Merci, au revoir.'


class VoiceTurn:
    def __init__(self, agi: Agi, root: Path, ledger: VoiceLedger):
        self.agi = agi
        self.root = root
        self.ledger = ledger
        self.keys = secrets()
        self.turns: list[dict[str, str]] = []

    def play_text(self, text: str) -> None:
        wav = synthesize(text, self.keys['openai'], self.root)
        if wav is None:
            return
        self.agi.stream(strip_ext(wav))

    def dialogue(self, prefix: str) -> None:
        history: list[dict[str, str]] = []
        empty_streak = 0
        for turn in range(MAX_TURNS):
            rec_path = (
                self.root / 'state/voice/records' / f'{prefix}-t{turn}.wav'
            )
            rec_path.parent.mkdir(parents=True, exist_ok=True)
            self.agi.record(
                strip_ext(rec_path),
                RECORD_TIMEOUT_MS,
                RECORD_SILENCE_S,
            )
            text = transcribe(rec_path, self.keys['openai'])
            if not text:
                empty_streak += 1
                if empty_streak >= 2:
                    self.play_text(CANNOT_HEAR)
                    return
                self.play_text(NOT_UNDERSTOOD)
                continue
            empty_streak = 0
            history.append({'role': 'user', 'content': text})
            reply = chat_reply(history, self.keys['openrouter'])
            if not reply:
                return
            history.append({'role': 'assistant', 'content': reply})
            self.turns.append({'user': text, 'serge': reply})
            self.play_text(reply)
            if re.search(r'au\s*revoir', reply, re.IGNORECASE):
                return

    def callback_menu(self, prefix: str) -> bool:
        """DTMF-1 callback offer. Returns True when callback requested."""
        menu_wav = synthesize(CALLBACK_MENU, self.keys['openai'], self.root)
        if menu_wav is None:
            return False
        digits = self.agi.get_data(strip_ext(menu_wav), 6000, 1)
        return digits == '1'

    def voicemail(self, prefix: str) -> Path:
        try:
            self.agi.stream('beep')
        except AgiHangup:
            raise
        rec_path = self.root / 'state/voice/records' / f'{prefix}-vbox.wav'
        rec_path.parent.mkdir(parents=True, exist_ok=True)
        self.agi.record(strip_ext(rec_path), VOICEMAIL_TIMEOUT_MS, 3)
        return rec_path

    def run_outbound(self, to_e164: str) -> dict[str, Any]:
        started = time.time()
        claim = self.ledger.claim_outbound(to_e164)
        cdr = (claim or {}).get('cdr_id', f'cdr_manual_{int(started)}')
        prefix = re.sub(r'[^A-Za-z0-9]+', '', cdr)
        self.agi.answer()
        pitch = (
            (claim or {}).get('message') or ''
        ).strip() or OUTBOUND_DEFAULT_PITCH
        if self.keys['openai']:
            self.play_text(pitch)
            self.dialogue(prefix)
            callback = self.callback_menu(prefix)
            recording = self.voicemail(prefix)
        else:
            callback = self.owner_greeting_fallback()
            recording = self.voicemail(prefix)
        return self.close(
            cdr, 'outbound', to_e164, callback, recording, started
        )

    def run_inbound(self, caller: str, did: str) -> dict[str, Any]:
        started = time.time()
        record = self.ledger.record_inbound(
            caller=caller or 'unknown', did=did
        )
        prefix = re.sub(r'[^A-Za-z0-9]+', '', record['cdr_id'])
        self.agi.answer()
        if self.keys['openai']:
            self.play_text(INBOUND_GREETING)
            self.dialogue(prefix)
            callback = self.callback_menu(prefix)
            recording = self.voicemail(prefix)
        else:
            callback = self.owner_greeting_fallback()
            recording = self.voicemail(prefix)
        return self.close(
            record['cdr_id'],
            'inbound',
            caller,
            callback,
            recording,
            started,
        )

    def owner_greeting_fallback(self) -> bool:
        """No TTS key: play owner greeting.wav when present. No menu."""
        greeting = config_root() / 'voice/greeting.wav'
        if greeting.is_file():
            self.agi.stream(strip_ext(greeting))
        return False

    def close(
        self,
        cdr: str,
        direction: str,
        peer: str,
        callback: bool,
        recording: Path,
        started: float,
    ) -> dict[str, Any]:
        try:
            self.play_text(GOODBYE)
        except AgiHangup:
            pass
        meta = {
            'cdr_id': cdr,
            'direction': direction,
            'peer': peer,
            'turns': self.turns,
            'callback_requested': callback,
            'recording': str(recording),
            'duration_s': int(time.time() - started),
            'ended_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }
        try:
            calls_dir = self.root / 'state/voice/calls'
            calls_dir.mkdir(parents=True, exist_ok=True)
            meta_path = calls_dir / f'{cdr}.json'
            meta_path.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False) + '\n',
                encoding='utf-8',
            )
            meta_path.chmod(0o600)
        except OSError:
            pass
        try:
            self.ledger.record_outcome(
                cdr,
                outcome='completed',
                duration_s=meta['duration_s'],
                recording_path=str(recording),
                callback_requested=callback,
            )
        except Exception:  # noqa: BLE001 — CDR write must not fail the call
            pass
        try:
            self.agi.hangup()
        except AgiHangup:
            pass
        return meta


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if len(args) < 2 or args[0] not in {'inbound', 'outbound'}:
        sys.stderr.write('usage: turn.py inbound <caller> [did]\n')
        sys.stderr.write('       turn.py outbound <callee>\n')
        return 2
    root = system_root()
    try:
        agi = Agi()
    except (OSError, ValueError):
        return 0
    turn = VoiceTurn(agi, root, VoiceLedger(default_ledger_path(root)))
    try:
        if args[0] == 'outbound':
            turn.run_outbound(args[1])
        else:
            caller = args[1]
            did = args[2] if len(args) > 2 else ''
            turn.run_inbound(caller, did)
    except AgiHangup:
        return 0
    except Exception as exc:  # noqa: BLE001 — never crash an AGI leg
        try:
            agi.verbose(f'serge voice error: {exc}')
            agi.hangup()
        except AgiHangup:
            pass
        return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
