#!/usr/bin/env python3
"""Régressions de la revue MC : sessions, réglages, décisions et navigation.

Le serveur et SQLite sont réels. Le catalogue de modèles est remplacé par
une réponse fixe. Aucun modèle ni service extérieur n'est appelé.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime
from unittest import mock

from playwright.sync_api import expect

from serge.db.store import open_db
from serge.mc.proj_economy import project_transactions_subscriptions
from serge.mc.proj_tickets import project_tickets
from serge.registry import load_ticket_types
from serge.tickets import create_ticket, publish
from serge.voice.ledger import VoiceLedger
from tests.mc_server_case import McBrowserCase, McServerCase
from tests.test_mc_pipeline_page import CATALOGUE


class ReviewApiTests(McServerCase):
    def test_policy_refuse_les_tailles_incoherentes_et_le_verrou(self):
        # Un réglage général s'enregistre seul (Q68) : la relation entre
        # tailles, les nombres non finis et le verrou d'un essai en cours
        # sont vérifiés à chaque réglage.
        cookie = self._auth_cookie()

        def regler(ident, value):
            return self._api_post(
                '/owner/api/reglage',
                {'cible': 'policy', 'id': ident, 'value': value},
                cookie,
            )[0]

        self.assertEqual(regler('testing.n_smoke_min', 77), 400)
        self.assertEqual(
            self._request(
                'GET', '/owner/api/state?page=p5', headers={'Cookie': cookie}
            )[0],
            200,
        )
        for value in [float('nan'), float('inf')]:
            self.assertEqual(regler('budget.monthly_eur', value), 400)
        with open_db(self.db_path) as conn:
            conn.execute(
                "INSERT INTO campaigns(id,venture_id,family,channel,state,n_target,created_at,updated_at) VALUES('running','v','named','email','RUNNING',10,'t','t')"
            )
        self.assertEqual(regler('testing.n_smoke_min', 35), 409)

    def test_nombres_refuses_et_formulaire_unicode(self):
        cookie = self._auth_cookie()
        self.assertEqual(
            self._api_post(
                '/owner/api/reglage',
                {
                    'cible': 'quota',
                    'id': 'places_de_test',
                    'value': '9' * 5000,
                },
                cookie,
            )[0],
            400,
        )
        for value in ['2.5', 'NaN', 'Infinity']:
            self.assertEqual(
                self._api_post(
                    '/owner/api/reglage',
                    {
                        'cible': 'invocation',
                        'invocation_id': 'formuler_a',
                        'name': 'nombre_idees',
                        'value': value,
                    },
                    cookie,
                )[0],
                400,
            )
        guide = 'é' * 4000
        status, _, body = self._api_post(
            '/owner/api/bouton',
            {'trigger_id': 'lancer_cycle', 'form': {'guide': guide}},
            cookie,
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(
            self._api_post(
                '/owner/api/pipeline/texte', {'body': guide}, cookie
            )[0],
            200,
        )
        self.assertEqual(
            self._api_post(
                '/owner/api/pipeline/texte', {'body': 'a' * 66000}, cookie
            )[0],
            413,
        )

    def test_audio_reserve_a_la_session(self):
        ledger_path = self.db_path.parent / 'voice.db'
        ledger = VoiceLedger(ledger_path, self.db_path)
        call = ledger.record_inbound(caller='+33600000000', did='+33100000000')
        audio = self.db_path.parent / 'audit.wav'
        audio.write_bytes(b'RIFF-audio-test')
        ledger.record_outcome(
            call['cdr_id'], outcome='completed', recording_path=str(audio)
        )
        path = f'/owner/api/voice/audio?cdr={call["cdr_id"]}&exp=9999999999&sig=ancienne-signature'
        cookie = self._auth_cookie()
        with mock.patch(
            'serge.voice.policy.default_ledger_path', return_value=ledger_path
        ):
            self.assertEqual(self._request('GET', path)[0], 401)
            self.assertEqual(
                self._request('GET', path, headers={'Cookie': cookie})[2],
                audio.read_bytes(),
            )
            self._request('POST', '/owner/logout', headers={'Cookie': cookie})
            self.assertEqual(
                self._request('GET', path, headers={'Cookie': cookie})[0], 401
            )

    def test_logout_ferme_le_flux_existant(self):
        cookie = self._auth_cookie()
        request = urllib.request.Request(
            self.base + '/owner/api/stream?page=p3', headers={'Cookie': cookie}
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            self.assertEqual(response.readline().strip(), b'event: section')
            self._request('POST', '/owner/logout', headers={'Cookie': cookie})
            # Le tick suivant envoie auth puis ferme la connexion.
            lines = []
            while True:
                line = response.readline()
                if not line:
                    break
                lines.append(line)
            self.assertIn(b'event: auth\n', lines)

    def test_tickets_actifs_complets_et_discussion_continue(self):
        types = load_ticket_types()
        with open_db(self.db_path) as conn:
            urgent = create_ticket(
                conn,
                types,
                'GUICHET',
                'Urgent',
                now='2020-01-01T00:00:00+00:00',
            )
            publish(conn, urgent)
            for n in range(55):
                ident = create_ticket(conn, types, 'FYI', f'Info {n}')
                publish(conn, ident)
            ids = [
                x['id']
                for x in project_tickets(
                    conn, {}, datetime.now(UTC).isoformat()
                )['items']
            ]
            self.assertIn(urgent, ids)
        cookie = self._auth_cookie()
        for message in ['Premier message', 'Deuxième message']:
            self.assertEqual(
                self._api_post(
                    '/owner/api/ticket/discuter',
                    {'ticket_id': urgent, 'message': message},
                    cookie,
                )[0],
                200,
            )
        status, _, body = self._request(
            'GET',
            f'/owner/api/ticket/carte?ticket={urgent}',
            headers={'Cookie': cookie},
        )
        self.assertEqual(status, 200)
        carte = json.loads(body)
        self.assertEqual(carte['boutons'], types['GUICHET']['buttons'])
        self.assertEqual(
            [e['message'] for e in carte['events'] if 'message' in e],
            ['Premier message', 'Deuxième message'],
        )
        self.assertEqual(
            self._api_post(
                '/owner/api/ticket/acte',
                {'ticket_id': urgent, 'acte': 'cest_fait'},
                cookie,
            )[0],
            200,
        )

    def test_mrr_ne_depend_pas_des_vingt_derniers_abonnements(self):
        with open_db(self.db_path) as conn:
            conn.execute(
                "INSERT INTO subscriptions(id,provider,amount_eur,period,status,created_at,updated_at) VALUES('old','stripe',19,'monthly','active','2020','2020')"
            )
            for n in range(21):
                conn.execute(
                    "INSERT INTO subscriptions(id,provider,amount_eur,period,status,created_at,updated_at) VALUES(?,'stripe',10,'monthly','cancelled','2026','2026')",
                    (f'new{n}',),
                )
            self.assertEqual(
                project_transactions_subscriptions(conn, {}, '')['mrr_eur'], 19
            )

    def test_actes_du_registre_et_catalogue_hors_ligne(self):
        cookie = self._auth_cookie()
        types = load_ticket_types()
        for typ, spec in types.items():
            with open_db(self.db_path) as conn:
                tid = create_ticket(
                    conn,
                    types,
                    typ,
                    'Question',
                    {'options_qcm': ['Oui', 'Non']},
                )
                publish(conn, tid)
            st, _, body = self._request(
                'GET',
                f'/owner/api/ticket/carte?ticket={tid}',
                headers={'Cookie': cookie},
            )
            self.assertEqual(json.loads(body)['boutons'], spec['buttons'])
            acte = spec['buttons'][0]
            if acte == 'discuter_fil':
                st, _, _ = self._api_post(
                    '/owner/api/ticket/discuter',
                    {'ticket_id': tid, 'message': 'Message libre'},
                    cookie,
                )
            else:
                st, _, _ = self._api_post(
                    '/owner/api/ticket/acte',
                    {'ticket_id': tid, 'acte': acte, 'note': 'Oui'},
                    cookie,
                )
            self.assertEqual(st, 200, (typ, acte))
        from kit.openrouter import OpenRouterError
        from serge.llm import catalog

        with mock.patch(
            'serge.llm.catalog._read_openrouter', return_value=CATALOGUE
        ):
            catalog.catalog()
        with mock.patch(
            'serge.llm.catalog._read_openrouter',
            side_effect=OpenRouterError('Panne simulée'),
        ):
            st, _, body = self._api_post(
                '/owner/api/pipeline/modele',
                {'tier': 'mid', 'model': 'new/model'},
                cookie,
            )
            self.assertEqual(st, 200, body)
            self.assertIn('non vérifié', json.loads(body)['warning'])
        catalog.clear_cache()


class ReviewBrowserTests(McBrowserCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch(
            'serge.llm.catalog._read_openrouter', return_value=CATALOGUE
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_brouillons_et_erreurs_reseau(self):
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(self.base + '/owner#/pipeline')
        expect(page.locator('[data-tier="smart"]')).to_be_visible()
        page.locator('[data-tier="smart"]').fill('openai/gpt-mini')
        page.locator('[data-max-price="mid"]').fill('2.25')
        with page.expect_response('**/owner/api/pipeline/modele'):
            page.locator('[data-tier="mid"]').locator(
                'xpath=../..'
            ).get_by_role('button', name='Enregistrer').click()
        expect(page.locator('[data-max-price="mid"]')).to_have_value('2.25')
        page.wait_for_timeout(2300)
        expect(page.locator('[data-tier="smart"]')).to_have_value(
            'openai/gpt-mini'
        )
        page.goto(self.base + '/owner#/policy')
        rows = page.locator('.ligne-reglage')
        expect(rows.first).to_be_visible()
        rows.nth(1).locator('input').fill('7')
        rows.first.locator('input').fill('1')
        with page.expect_response('**/owner/api/reglage'):
            rows.first.get_by_role('button', name='Enregistrer').click()
        page.wait_for_timeout(2300)
        expect(rows.nth(1).locator('input')).to_have_value('7')
        page.goto(self.base + '/owner#/ecoute')
        guide = page.locator('[data-champ="guide"]')
        expect(guide).to_be_visible()
        guide.fill('Brouillon conservé')
        with open_db(self.db_path) as conn:
            conn.execute(
                "INSERT INTO ventures(id,name,lifecycle,created_at,updated_at) VALUES('chosen','Choisi','POC_SELECTED','t','t')"
            )
        page.wait_for_timeout(2300)
        expect(guide).to_have_value('Brouillon conservé')
        page.goto(self.base + '/owner#/pipeline')
        expect(page.locator('[data-tier="mid"]')).to_be_visible()
        page.route('**/owner/api/pipeline/modele', lambda route: route.abort())
        page.locator('[data-tier="mid"]').locator('xpath=../..').get_by_role(
            'button', name='Enregistrer'
        ).click()
        expect(page.locator('.toast-erreur').last).to_contain_text(
            'injoignable'
        )

    def test_policy_jours_modales_et_palette(self):
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(self.base + '/owner?snapshot=1#/policy')
        expect(page.locator('.corps-policy')).to_be_visible()
        # Les jours d'appel ne sont plus dans la policy (Q68 : rien ne les
        # lisait ; le lot 8 les remet avec la voix) : le champ des jours est
        # vérifié seul, avec le mardi.
        result = page.evaluate(
            """async () => { const {champPolicy} = await import('/static/mc/policy_form.js'); const spec = {titre: 'Jours', widget: 'jours', choix: [['mon', 'lun'], ['tue', 'mar'], ['wed', 'mer']]}; const champ = champPolicy('calling_zones.FR.voice_days', spec, ['mon', 'tue']); document.body.append(champ); return champ._lire(); }"""
        )
        self.assertEqual(result, ['mon', 'tue'])
        # « Demander un changement » est retiré (Q68) : le confinement du
        # focus est vérifié sur la fenêtre commune à toutes les questions.
        page.evaluate(
            """async () => { const {promptModal} = await import('/static/mc/components.js'); promptModal(document.body, {title: 'Essai', message: 'Focus', fields: [{nom: 'a', label: 'A'}, {nom: 'b', label: 'B'}], confirm: 'OK'}); }"""
        )
        expect(page.get_by_role('alertdialog')).to_have_attribute(
            'aria-modal', 'true'
        )
        for _ in range(7):
            page.keyboard.press('Tab')
            self.assertTrue(
                page.evaluate("!!document.activeElement.closest('.modale')")
            )
        page.keyboard.press('Escape')
        page.goto(self.base + '/owner#/live')
        page.keyboard.press('Control+k')
        page.locator('.cmdk-input').fill('Système')
        page.keyboard.press('Enter')
        expect(page.locator('[data-section="email"]')).to_be_visible()

    def test_carte_reactive_et_navigation_sans_course(self):
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(self.base + '/owner?snapshot=1#/live')
        expect(page.locator('.noeud').first).to_be_visible()
        for width in [1440, 1280, 390]:
            page.set_viewport_size({'width': width, 'height': 900})
            page.wait_for_timeout(100)
            overlaps = page.evaluate(
                """() => { const nodes = [...document.querySelectorAll('.noeud')].map(n => n.getBoundingClientRect()); return nodes.some((a,i) => nodes.slice(i+1).some(b => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top)); }"""
            )
            self.assertFalse(overlaps, width)
        for _ in range(3):
            page.evaluate("location.hash='#/mind'")
            expect(page.locator('[data-section="matrice"]')).to_be_visible()
            page.evaluate("location.hash='#/live'")
            expect(page.locator('.btn-kill-serge')).to_be_visible()
        page.locator('.btn-kill-serge').click()
        expect(page.locator('.modale')).to_have_count(1)
        page.keyboard.press('Escape')
        page.evaluate(
            """() => { const orig = fetch; window.fetch = (...args) => String(args[0]).startsWith('/owner/api/objet') ? new Promise(r => setTimeout(() => r(orig(...args)), 600)) : orig(...args); location.hash = '#/objet/llm/formuler_a'; }"""
        )
        page.wait_for_timeout(100)
        page.evaluate("location.hash='#/mind'")
        page.wait_for_timeout(1000)
        expect(page.locator('[data-section="matrice"]')).to_be_visible()
        expect(page.locator('.fiche-objet')).to_have_count(0)
        # Quitter aussi la page montée pendant la requête lente : son
        # nettoyage doit rester enregistré une fois l'ancienne fiche finie.
        page.evaluate("location.hash='#/live'")
        expect(page.locator('.btn-kill-serge')).to_be_visible()
        page.evaluate("location.hash='#/objet/llm/formuler_a'")
        page.wait_for_timeout(100)
        page.evaluate("location.hash='#/live'")
        page.wait_for_timeout(1000)
        page.evaluate("location.hash='#/mind'")
        expect(page.locator('[data-section="matrice"]')).to_be_visible()
        page.evaluate("location.hash='#/live'")
        expect(page.locator('.btn-kill-serge')).to_be_visible()
        page.locator('.btn-kill-serge').click()
        expect(page.locator('.modale')).to_have_count(1)
        page.keyboard.press('Escape')
        page.goto(self.base + '/owner#/pipeline')
        row = page.locator('[data-pipeline="liens"] tbody tr').first
        expect(row).to_be_visible()
        row.focus()
        page.keyboard.press('Enter')
        expect(page.locator('.fiche-objet')).to_be_visible()

    def test_qcm_et_session_revoquee(self):
        with open_db(self.db_path) as conn:
            tid = create_ticket(
                conn,
                load_ticket_types(),
                'QNA',
                'Quel canal ?',
                {'options_qcm': ['Email', 'Voix']},
            )
            publish(conn, tid)
        context = self._auth_context()
        page = context.new_page()
        self._watch_errors(page)
        page.goto(self.base + '/owner#/objet/ticket/' + tid)
        page.get_by_role('button', name='Choisir une réponse').click()
        page.locator('.modale select').select_option('Email')
        with page.expect_response('**/owner/api/ticket/acte') as response:
            page.locator('.modale').get_by_role(
                'button', name='Choisir une réponse'
            ).click()
        self.assertEqual(response.value.status, 200)
        with open_db(self.db_path) as conn:
            events = conn.execute(
                "SELECT payload_json FROM ticket_events WHERE ticket_id=? AND kind='transition.approved'",
                (tid,),
            ).fetchall()
            self.assertEqual(json.loads(events[0][0])['note'], 'Email')
        page.goto(self.base + '/owner#/live')
        expect(page.locator('#health')).to_have_attribute('data-etat', 'ok')
        context.request.post(self.base + '/owner/logout')
        expect(page.locator('#health')).to_have_attribute(
            'data-etat', 'ko', timeout=7000
        )
        expect(page.locator('#health')).to_have_attribute(
            'title', 'Session expirée — reconnecte-toi'
        )

    def test_actions_ticket_urgent_et_curation_lecon(self):
        with open_db(self.db_path) as conn:
            ident = create_ticket(
                conn,
                load_ticket_types(),
                'GUICHET',
                'Action requise',
                ttl_minutes=5,
            )
            publish(conn, ident)
            conn.execute(
                "INSERT INTO lessons(id,statement,created_at,updated_at) VALUES('review_lesson','Ancienne leçon','t','t')"
            )
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(self.base + '/owner#/live')
        page.locator('.lien-urgent').first.click()
        expect(page.get_by_role('button', name='C’est fait')).to_be_visible()
        page.get_by_role('button', name='C’est fait').click()
        with page.expect_response('**/owner/api/ticket/acte'):
            page.locator('.modale').get_by_role(
                'button', name='C’est fait'
            ).click()
        with open_db(self.db_path) as conn:
            self.assertEqual(
                conn.execute(
                    'SELECT state FROM tickets WHERE id=?', (ident,)
                ).fetchone()[0],
                'APPROVED',
            )
        page.goto(self.base + '/owner#/objet/lesson/review_lesson')
        page.get_by_role('button', name='Modifier la leçon').click()
        page.locator('.modale input').fill('Nouvelle leçon')
        with page.expect_response('**/owner/api/memory/lesson'):
            page.locator('.modale').get_by_role(
                'button', name='Valider'
            ).click()
        expect(page.locator('#page')).to_contain_text('Nouvelle leçon')
        page.get_by_role('button', name='Jeter la leçon').click()
        with page.expect_response('**/owner/api/memory/lesson'):
            page.locator('.modale').get_by_role(
                'button', name='Confirmer'
            ).click()
        expect(page.locator('.memory-tabs')).to_be_visible()
