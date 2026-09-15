#!/usr/bin/env python3
"""Boîte : mail canon + SMS brut, refus si volet hors contrat identité."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.boite import lire_boite  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.sms.inbox import SmsInbox  # noqa: E402


class BoiteTests(unittest.TestCase):
    def test_mail_et_sms_bruts(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        conn.execute(
            'INSERT INTO inbound_events(id, campaign_id, contact_id,'
            ' channel, native_type, signal, received_at, payload_json)'
            " VALUES('e1','','p1','email','mail','reply',"
            "'2026-09-15T10:00:00+00:00',?)",
            (json.dumps({'from': 'a@x.io', 'text': 'code 123456'}),),
        )
        with tempfile.TemporaryDirectory() as tmp:
            inbox = SmsInbox(Path(tmp) / 'sms.db')
            # ingest needs signature — write row directly
            inbox.db_path.parent.mkdir(parents=True, exist_ok=True)
            raw = sqlite3.connect(inbox.db_path)
            raw.execute(
                'INSERT INTO inbound_sms(provider_message_id, sender_hash,'
                ' body_hash, purpose, otp, received_at, signature_verified,'
                " sender, body) VALUES('m1','h','b','OBSERVATION','',"
                "'2026-09-15T11:00:00+00:00',1,'+33600','ton code 99')"
            )
            raw.commit()
            raw.close()
            vu = lire_boite(conn, sms=inbox, limite=10)
        self.assertEqual(vu['mails'][0]['corps'], 'code 123456')
        self.assertEqual(vu['sms'][0]['corps'], 'ton code 99')
        self.assertEqual(vu['sms'][0]['expediteur'], '+33600')
