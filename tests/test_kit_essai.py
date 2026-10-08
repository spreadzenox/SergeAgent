#!/usr/bin/env python3
"""Le kit d'essai de bout en bout (lot 8, PR 4, décision Q79).

Seuls le canal e-mail, le pont téléphonique (sa réponse à « composer ») et
le modèle sont des faux ; le pipeline en base, l'interpréteur, les
garde-fous et le journal des appels sont réels. Les coordonnées sont
fausses : les vraies ne sont tapées que dans Mission Control.

Scénarios :
- « Lancer un essai » : un business bidon avec sa demi-fiche produit, la
  fiche de la personne avec son accord « test », puis un premier e-mail
  rédigé et envoyé, et un premier appel composé, même un dimanche ;
- un deuxième essai remplace le business bidon ;
- un numéro qui n'est pas au format international : l'essai échoue avec
  la raison, rien ne part.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.channels.adapters import ADAPTERS  # noqa: E402
from serge.channels.base import Adapter, Outgoing  # noqa: E402
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.interpreter.flow import fire_button  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.privacy import subject_hash  # noqa: E402
from serge.voice.ledger import VoiceLedger  # noqa: E402
from serge.voice.policy import default_ledger_path  # noqa: E402

DIMANCHE = '2026-09-06T10:30:00+00:00'
FORMULAIRE = {
    'nom': 'Essai Testeur',
    'e-mail': 'essai@exemple.fr',
    'téléphone (+33…)': '+33600000001',
}
BUT = 'Présenter Devis Vocal et obtenir un rendez-vous.'


class FauxModele:
    """Rédige le premier e-mail et le but du premier appel."""

    def __init__(self) -> None:
        self.recu: list[str] = []

    def __call__(self, _key, _model, messages, tools=None, **_kw):
        system, user = messages[0]['content'], messages[1]['content']
        self.recu.append(user)
        if 'Tu écris le premier e-mail' in system:
            data: dict[str, Any] = {
                'subject': 'Vos devis en 10 minutes',
                'body': 'Bonjour, Devis Vocal met vos devis en page.',
            }
        else:
            data = {'body': BUT}
        return ChatResult(json.dumps(data), 10, 10, 'faux', 1)


class KitEssaiTests(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        root = Path(dossier.name)
        instance = root / 'instance.toml'
        instance.write_text('[features]\nphone_voice = true\n')
        patcher = mock.patch.dict(
            os.environ,
            {
                'SERGE_SYSTEM_ROOT': str(root),
                'SERGE_INSTANCE_FILE': str(instance),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = open_db(default_canon_path())
        self.addCleanup(self.conn.close)
        set_heartbeat(self.conn, True)
        self.conn.commit()
        self.ledger = VoiceLedger(default_ledger_path())
        self.mails: list[Outgoing] = []
        self.composes: list[dict[str, Any]] = []
        faux_mail = Adapter(
            'email',
            'E-mail',
            '',
            'email',
            'x.py',
            lambda m: self.mails.append(m) or f'<{m.touch_id}@serge>',
            lambda _m: '',
        )
        for patcher in (
            mock.patch.dict(ADAPTERS, {'email': faux_mail}),
            mock.patch('serge.channels.voice._bridge', side_effect=self._pont),
            mock.patch(
                'serge.voice.bridge.originate', side_effect=self._composer
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.modele = FauxModele()

    def _pont(
        self, path: str, payload: dict[str, str] | None = None
    ) -> dict[str, Any]:
        from serge.voice.bridge import originate_for_task

        if path.startswith('/calls'):
            return {'calls': []}
        return originate_for_task(dict(payload or {}))

    def _composer(self, **demande: Any) -> dict[str, Any]:
        self.composes.append(demande)
        return {'decision': 'allowed', 'originated': True, 'cdr_id': 'cdr_1'}

    def _un(self, sql: str, params: tuple = ()) -> tuple:
        return tuple(self.conn.execute(sql, params).fetchone())

    def _essai(self, formulaire: dict[str, str]) -> None:
        self.assertIsNotNone(
            fire_button(self.conn, 'bouton_lancer_essai', formulaire)
        )
        self.conn.commit()
        # Un dimanche : l'appel d'essai part quand même (accord « test »).
        with mock.patch('serge.guards.check.utcnow', return_value=DIMANCHE):
            for _ in range(20):
                if (
                    process_one(self.conn, 'conversations', caller=self.modele)
                    is None
                ):
                    break

    def test_l_essai_ecrit_et_appelle_meme_un_dimanche(self) -> None:
        self._essai(FORMULAIRE)
        echecs = self.conn.execute(
            "SELECT invocation_id, last_error FROM tasks WHERE status='failed'"
        ).fetchall()
        self.assertEqual([tuple(e) for e in echecs], [])
        venture, nom = self._un(
            "SELECT id, name FROM ventures WHERE lifecycle='TEST'"
        )
        self.assertEqual(nom, 'Devis Vocal')
        self.assertIn(
            'dicte son devis',
            self._un(
                'SELECT summary FROM product_sheets WHERE venture_id=?',
                (venture,),
            )[0],
        )
        self.assertEqual(
            self._un(
                'SELECT COUNT(*) FROM product_faq WHERE venture_id=?',
                (venture,),
            ),
            (2,),
        )
        contact, etape = self._un(
            "SELECT id, funnel_state FROM contacts WHERE display='Essai Testeur'"
        )
        self.assertEqual(etape, 'CONTACTING')
        self.assertEqual(
            self._un(
                "SELECT basis FROM consents WHERE channel='voice'"
                ' AND subject_hash=?',
                (subject_hash('+33600000001'),),
            ),
            ('test',),
        )
        self.assertEqual(
            [(m.address, m.subject) for m in self.mails],
            [('essai@exemple.fr', 'Vos devis en 10 minutes')],
        )
        self.assertEqual(
            [(c['to_e164'], c['message']) for c in self.composes],
            [('+33600000001', BUT)],
        )
        envois = self.conn.execute(
            'SELECT channel, status FROM touches WHERE contact_id=?'
            ' ORDER BY channel',
            (contact,),
        ).fetchall()
        self.assertEqual(
            [tuple(e) for e in envois], [('email', 'sent'), ('voice', 'sent')]
        )
        # Le modèle a lu la fiche produit pour écrire.
        self.assertIn('Pas d', self.modele.recu[0])

    def test_un_deuxieme_essai_remplace_le_business_bidon(self) -> None:
        self._essai(FORMULAIRE)
        premier = self._un("SELECT id FROM ventures WHERE lifecycle='TEST'")
        self._essai(FORMULAIRE)
        self.assertEqual(
            self._un("SELECT COUNT(*) FROM ventures WHERE lifecycle='TEST'"),
            (1,),
        )
        self.assertNotEqual(
            self._un("SELECT id FROM ventures WHERE lifecycle='TEST'"), premier
        )
        self.assertEqual(len(self.mails), 2)

    def test_un_numero_mal_forme_arrete_l_essai(self) -> None:
        self._essai({**FORMULAIRE, 'téléphone (+33…)': '06 00 00 00 01'})
        (erreur,) = self._un(
            "SELECT last_error FROM tasks WHERE status='failed'"
            " AND invocation_id='creer_contact_essai'"
        )
        self.assertIn('format international', erreur)
        self.assertEqual(self.mails, [])
        self.assertEqual(self.composes, [])


if __name__ == '__main__':
    unittest.main()
