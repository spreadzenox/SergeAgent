#!/usr/bin/env python3
"""Turn-based voice call leg (Asterisk AGI entry). Robust fallback path.

Le secours de la voix en direct (``s2s.py``) : quand la session temps réel
n'est pas joignable (ou lâche en plein appel), l'appel passe ici, tour par
tour (enregistrer, transcrire, répondre, lire) — jamais un plantage,
jamais un silence, jamais un raccrochage sec.

C'est le même agent vocal, réglé en base (``serge/voice/agent.py``) : son
prompt, la fiche du contact, son modèle de secours (``modele_secours``) et
son nombre de tours (``tours_secours``). Ses phrases fixes (accueil, menu
de rappel, « je ne vous entends pas »…) sont des textes de la page
Pipeline. À la fin, ce qui s'est dit entre dans le fil du contact.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from serge.coupe_circuit import serge_demarre  # noqa: E402
from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.interpreter.intro import serge_text  # noqa: E402
from serge.voice.agent import (  # noqa: E402
    Call,
    finish_call,
    hear,
    instructions,
    settings,
    start_call,
)
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

RECORD_TIMEOUT_MS = 7000
RECORD_SILENCE_S = 2
VOICEMAIL_TIMEOUT_MS = 45000


class VoiceTurn:
    def __init__(
        self,
        agi: Agi,
        root: Path,
        ledger: VoiceLedger,
        canon: sqlite3.Connection,
    ):
        self.agi = agi
        self.root = root
        self.ledger = ledger
        self.canon = canon
        self.keys = secrets()
        self.turns: list[dict[str, str]] = []
        self.call: Call | None = None

    def text(self, ident: str) -> str:
        """Une phrase fixe du secours (page Pipeline)."""
        return serge_text(self.canon, ident)

    def play_text(self, text: str) -> None:
        if not text:
            return
        wav = synthesize(text, self.keys['openai'], self.root)
        if wav is None:
            return
        self.agi.stream(strip_ext(wav))

    def dialogue(self, prefix: str) -> None:
        cfg = settings(self.canon, self.call) if self.call else {}
        system = instructions(self.canon, self.call) if self.call else ''
        history: list[dict[str, str]] = []
        empty_streak = 0
        for turn in range(int(cfg.get('tours_secours') or 0)):
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
                    self.play_text(self.text('voice_backup_cannot_hear'))
                    return
                self.play_text(self.text('voice_backup_not_understood'))
                continue
            empty_streak = 0
            history.append({'role': 'user', 'content': text})
            reply = chat_reply(
                history,
                self.keys['openrouter'],
                system,
                cfg.get('modele_secours', ''),
            )
            if not reply:
                return
            history.append({'role': 'assistant', 'content': reply})
            self.turns.append({'user': text, 'serge': reply})
            if self.call:
                hear(self.call, 'Contact', text)
                hear(self.call, 'Serge', reply)
            self.play_text(reply)
            if re.search(r'au\s*revoir', reply, re.IGNORECASE):
                return

    def callback_menu(self, prefix: str) -> bool:
        """DTMF-1 callback offer. Returns True when callback requested."""
        menu = self.text('voice_backup_menu')
        menu_wav = (
            synthesize(menu, self.keys['openai'], self.root) if menu else None
        )
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
        claim = self.ledger.claim_outbound(to_e164) or {}
        cdr = claim.get('cdr_id') or f'cdr_manual_{int(started)}'
        self.call = start_call(
            self.canon,
            'outbound',
            to_e164,
            cdr,
            str(claim.get('task_id') or ''),
        )
        prefix = re.sub(r'[^A-Za-z0-9]+', '', cdr)
        self.agi.answer()
        pitch = str(claim.get('message') or '').strip() or self.text(
            'voice_backup_pitch'
        )
        if self.keys['openai']:
            self.play_text(pitch)
            if self.call:
                hear(self.call, 'Serge', pitch)
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
        self.call = start_call(self.canon, 'inbound', caller, record['cdr_id'])
        prefix = re.sub(r'[^A-Za-z0-9]+', '', record['cdr_id'])
        self.agi.answer()
        if self.keys['openai']:
            greeting = self.text('voice_backup_greeting')
            self.play_text(greeting)
            if self.call:
                hear(self.call, 'Serge', greeting)
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
            self.play_text(self.text('voice_backup_goodbye'))
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
            if self.call:
                finish_call(self.canon, self.call)
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
    if not serge_demarre():
        # Serge arrêté dans Mission Control : on ne décroche pas.
        agi.hangup()
        return 0
    canon = open_db(default_canon_path())
    turn = VoiceTurn(agi, root, VoiceLedger(default_ledger_path(root)), canon)
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
    finally:
        canon.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
