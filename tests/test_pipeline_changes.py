#!/usr/bin/env python3
"""Les modifications d'objets déjà en base (section ``changes``).

Scénarios :
- une modification passe une seule fois, et son résultat est noté ;
- une valeur changée dans Mission Control est gardée ;
- une instance neuve, déjà à jour, n'est pas touchée ;
- une instance du lot 7 telle qu'elle a été déployée (25 tours d'outils
  pour « Explorer le web », 300 lignes par page, anciens prompts) reçoit
  les réglages qui renvoient moins de jetons, et les réglages nouveaux ;
- une instance déployée avant les réglages de recommandation (niveaux de
  modèle sans prix maximum) les reçoit, sans écraser un prix que Julien a
  déjà changé ;
- un outil nouveau s'ajoute une seule fois à une invocation déjà en base,
  à la fin de ses outils, avec ses paramètres ;
- une modification mal écrite est refusée ;
- une instance de la PR 4 du lot 10 perd le rythme des relances dans le
  plan d'un POC (Q37) : le champ de la réponse, sa colonne écrite et lue,
  et son paragraphe du prompt ; une instance neuve n'a rien à retirer ;
- une instance de la PR 7 passe de Hostinger à Cloudflare et à la carte
  chiffrée du coffre ; des secrets changés dans Mission Control sont
  gardés ;
- une instance du lot 11 reçoit le lot 12 : le plan d'un POC perd son
  nombre de prospects et choisit un canal branché, les valeurs d'essai et
  les couloirs des liens arrivent, les boutons d'essai de la page Système
  sont retirés ; sa base renomme la phase des campagnes ;
- le serveur du 19 novembre 2026 retrouve le produit d'un business dans
  Stripe par la clé de recherche de son prix, plus par la recherche ;
- le serveur du 20 novembre 2026 reçoit le bouton « Créer un compte web »
  corrigé : le libellé du site, le pseudo voulu, et sa consigne ;
- le même serveur, après l'inscription ratée sur X : le téléphone ne se
  donne que si le site l'exige, et les essais de message acceptent un
  pseudo ; un libellé changé dans Mission Control est gardé ;
- le serveur du 21 novembre 2026 apprend que le téléphone est exigé quand
  l'inscription n'offre que lui, et qu'un champ de connexion ne sert pas à
  s'inscrire.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.pipeline_changes import apply_changes  # noqa: E402
from serge.pipeline_seed import ensure_pipeline, seed_pipeline  # noqa: E402
from serge.policy import config_dir, read_yaml_file  # noqa: E402
from serge.seed_base import PipelineSeedError  # noqa: E402


def _changement(de: int, vers: int, ident: str = 'tours') -> list[dict]:
    return [
        {
            'id': ident,
            'table': 'invocations',
            'where': {'id': 'explorer_web'},
            'set': {'max_tool_turns': {'from': de, 'to': vers}},
        }
    ]


class ChangesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def _tours(self) -> int:
        return int(
            self.conn.execute(
                "SELECT max_tool_turns FROM invocations WHERE id='explorer_web'"
            ).fetchone()[0]
        )

    def _resultat(self, ident: str) -> str:
        return str(
            self.conn.execute(
                'SELECT result FROM pipeline_changes WHERE id=?', (ident,)
            ).fetchone()[0]
        )

    def test_une_modification_passe_une_seule_fois(self) -> None:
        apply_changes(self.conn, _changement(10, 7))
        self.assertEqual(self._tours(), 7)
        self.assertEqual(self._resultat('tours'), 'max_tool_turns : 10 → 7')
        self.conn.execute(
            "UPDATE invocations SET max_tool_turns=10 WHERE id='explorer_web'"
        )
        apply_changes(self.conn, _changement(10, 7))
        self.assertEqual(self._tours(), 10)

    def test_une_valeur_changee_dans_mission_control_est_gardee(self) -> None:
        self.conn.execute(
            "UPDATE invocations SET max_tool_turns=4 WHERE id='explorer_web'"
        )
        apply_changes(self.conn, _changement(10, 7))
        self.assertEqual(self._tours(), 4)
        self.assertIn('changé dans Mission Control', self._resultat('tours'))

    def test_une_instance_neuve_est_deja_a_jour(self) -> None:
        resultats = dict(
            self.conn.execute('SELECT id, result FROM pipeline_changes')
        )
        self.assertEqual(
            resultats['lot7_explorer_10_tours'], 'max_tool_turns déjà à jour'
        )
        self.assertEqual(
            resultats['lot7_formuler_a_plusieurs_pages'], 'prompt déjà à jour'
        )
        self.assertEqual(
            resultats['voix_email_du_contact'], 'email_du_contact déjà là'
        )

    def test_un_outil_nouveau_s_ajoute_une_seule_fois(self) -> None:
        outil = {
            'tool': 'fiche_contact',
            'mode': 'given',
            'label': 'Sa fiche',
            'params': {
                'contact_id': {'source': 'task', 'value': 'contact_id'}
            },
        }
        self.conn.execute(
            "DELETE FROM invocation_tools WHERE invocation_id='explorer_web'"
            " AND tool_id='fiche_contact'"
        )
        changes = [
            {
                'id': 'outil',
                'invocation': 'explorer_web',
                'add_tools': [outil],
            },
            {'id': 'absente', 'invocation': 'inconnue', 'add_tools': [outil]},
        ]
        apply_changes(self.conn, changes)
        self.assertEqual(self._resultat('outil'), 'fiche_contact ajouté')
        self.assertEqual(self._resultat('absente'), 'objet absent')
        lien, position = self.conn.execute(
            'SELECT id, position FROM invocation_tools'
            " WHERE invocation_id='explorer_web' AND tool_id='fiche_contact'"
        ).fetchone()
        self.assertEqual(
            position,
            self.conn.execute(
                'SELECT MAX(position) FROM invocation_tools'
                " WHERE invocation_id='explorer_web'"
            ).fetchone()[0],
        )
        self.assertEqual(
            self.conn.execute(
                'SELECT param_name, source, value FROM invocation_tool_params'
                ' WHERE invocation_tool_id=?',
                (lien,),
            ).fetchall(),
            [('contact_id', 'task', 'contact_id')],
        )
        with self.assertRaises(PipelineSeedError):
            apply_changes(
                self.conn,
                [{'id': 'mal', 'invocation': 'explorer_web', 'add_tools': {}}],
            )
        # Les champs d'une réponse et les valeurs d'une écriture : une
        # invocation ou une écriture absente est notée, une forme fausse
        # est refusée.
        apply_changes(
            self.conn,
            [
                {
                    'id': 'sortie_absente',
                    'invocation': 'inconnue',
                    'add_outputs': [{'path': 'x', 'type': 'text'}],
                },
                {
                    'id': 'ecriture_absente',
                    'invocation': 'explorer_web',
                    'write': 99,
                    'add_write_values': {'x': {'source': 'fixed'}},
                },
            ],
        )
        self.assertEqual(self._resultat('sortie_absente'), 'objet absent')
        self.assertEqual(
            self._resultat('ecriture_absente'), 'écriture absente'
        )
        for mauvais in (
            {'add_outputs': [{'path': 'x'}]},
            {'write': 'deux', 'add_write_values': {}},
        ):
            with self.assertRaises(PipelineSeedError, msg=mauvais):
                apply_changes(
                    self.conn,
                    [{'id': 'mal2', 'invocation': 'explorer_web', **mauvais}],
                )

    def test_une_modification_mal_ecrite_est_refusee(self) -> None:
        for mauvais in (
            {'table': 'ventures'},
            {'set': {'colonne_inconnue': {'from': 1, 'to': 2}}},
            {'where': {}},
        ):
            change = {**_changement(10, 7, 'mauvais')[0], **mauvais}
            with self.assertRaises(PipelineSeedError, msg=mauvais):
                apply_changes(self.conn, [change])


class InstanceDuLot7Tests(unittest.TestCase):
    """Le serveur de Julien, tel que le lot 7 l'a laissé."""

    def test_elle_recoit_les_reglages_qui_renvoient_moins_de_jetons(
        self,
    ) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        anciens = {
            c['where']['id']: c['set']['prompt']['from']
            for c in data['changes']
            if 'from' in c.get('set', {}).get('prompt', {})
        }
        for ident, tours in (
            ('explorer_web', 25),
            ('formuler_a', 10),
            ('formuler_b', 10),
        ):
            conn.execute(
                'UPDATE invocations SET max_tool_turns=?, prompt=? WHERE id=?',
                (tours, anciens[ident].strip(), ident),
            )
        conn.executescript(
            "UPDATE invocation_tools SET max_calls='' WHERE tool_id="
            "'lire_page_entiere' AND invocation_id LIKE 'formuler_%';"
            "UPDATE invocation_settings SET value='300' WHERE"
            " name='lignes_page_entiere';"
            "DELETE FROM invocation_settings WHERE name='pages_entieres_max';"
            'DELETE FROM pipeline_changes;'
        )
        conn.execute(
            "UPDATE triggers SET confirm_text=? WHERE id='bouton_abandonner_cycle'",
            (
                'Le cycle ouvert est fermé, pour pouvoir en lancer un autre.'
                ' Ses tâches déjà en file continuent, mais ne peuvent plus le'
                ' fermer.',
            ),
        )
        ensure_pipeline(conn)
        question = conn.execute(
            "SELECT confirm_text FROM triggers WHERE id='bouton_abandonner_cycle'"
        ).fetchone()[0]
        self.assertIn('tâches en attente sont annulées', question)
        tours = dict(
            conn.execute(
                'SELECT id, max_tool_turns FROM invocations WHERE id IN'
                " ('explorer_web', 'formuler_a', 'formuler_b')"
            )
        )
        self.assertEqual(
            tours, {'explorer_web': 10, 'formuler_a': 5, 'formuler_b': 5}
        )
        self.assertEqual(
            conn.execute(
                'SELECT DISTINCT max_calls FROM invocation_tools'
                " WHERE tool_id='lire_page_entiere'"
                " AND invocation_id LIKE 'formuler_%'"
            ).fetchall(),
            [('pages_entieres_max',)],
        )
        reglages = conn.execute(
            'SELECT invocation_id, name, value FROM invocation_settings'
            " WHERE name IN ('lignes_page_entiere', 'pages_entieres_max')"
            ' ORDER BY invocation_id, name'
        ).fetchall()
        self.assertEqual(
            reglages,
            [
                ('formuler_a', 'lignes_page_entiere', '150'),
                ('formuler_a', 'pages_entieres_max', '10'),
                ('formuler_b', 'lignes_page_entiere', '150'),
                ('formuler_b', 'pages_entieres_max', '10'),
            ],
        )
        prompt = conn.execute(
            "SELECT prompt FROM invocations WHERE id='formuler_b'"
        ).fetchone()[0]
        self.assertIn("Demande plusieurs pages d'un coup", prompt)


class NiveauxDeModeleTests(unittest.TestCase):
    """Le prix maximum et la tolérance des niveaux, sur une instance existante."""

    def _niveaux(self, conn: sqlite3.Connection) -> dict[str, tuple]:
        return {
            tier: (price, pct, model)
            for tier, price, pct, model in conn.execute(
                'SELECT tier, max_price_usd, tolerance_pct, model'
                ' FROM llm_models'
            )
        }

    def test_une_instance_neuve_a_les_valeurs_de_depart(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        self.assertEqual(
            self._niveaux(conn),
            {
                'fast': (0.3, 85, ''),
                'mid': (1.5, 95, ''),
                'smart': (8.0, 95, ''),
                'code': (12.0, 100, 'anthropic/claude-opus-5.5'),
                'web': (3.0, 95, 'anthropic/claude-sonnet-5.5'),
            },
        )

    def test_une_instance_existante_les_recoit_sans_ecraser_julien(
        self,
    ) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        # L'instance telle qu'elle était avant : niveaux sans réglage, un
        # modèle choisi sur le niveau moyen, un prix déjà changé à la main,
        # et pas encore de niveau « code » (lot 10) ni « web » (lot 11).
        conn.executescript(
            "DELETE FROM llm_models WHERE tier IN ('code', 'web');"
            'UPDATE llm_models SET max_price_usd=0, tolerance_pct=95;'
            "UPDATE llm_models SET model='a/choisi' WHERE tier='mid';"
            "UPDATE llm_models SET max_price_usd=2.5 WHERE tier='smart';"
            "DELETE FROM pipeline_changes WHERE id LIKE 'modele_%';"
        )
        ensure_pipeline(conn)
        self.assertEqual(
            self._niveaux(conn),
            {
                'fast': (0.3, 85, ''),
                'mid': (1.5, 95, 'a/choisi'),
                'smart': (2.5, 95, ''),
                'code': (12.0, 100, 'anthropic/claude-opus-5.5'),
                'web': (3.0, 95, 'anthropic/claude-sonnet-5.5'),
            },
        )
        resultats = dict(
            conn.execute(
                'SELECT id, result FROM pipeline_changes'
                " WHERE id LIKE 'modele_%'"
            )
        )
        self.assertIn(
            'gardé (changé dans Mission Control)',
            resultats['modele_smart_prix_max'],
        )
        # Rejouée, elle ne change plus rien.
        ensure_pipeline(conn)
        self.assertEqual(self._niveaux(conn)['smart'][0], 2.5)


class PlanSansRelancesTests(unittest.TestCase):
    """Une instance où « Concevoir le POC » écrit encore les relances."""

    IDS = (
        'lot10_plan_poc_sans_relances_prompt',
        'lot10_plan_poc_sans_relances_role',
        'lot10_plan_poc_sans_relances_reponse',
        'lot10_plan_poc_sans_relances_ecriture',
        'lot10_plan_sans_relances_lu',
    )

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.changes = [
            c
            for c in read_yaml_file(config_dir() / 'pipeline.yaml')['changes']
            if c['id'] in self.IDS
        ]

    def _etat(self) -> tuple:
        c = self.conn
        return (
            c.execute(
                'SELECT COUNT(*) FROM invocation_output_fields'
                " WHERE invocation_id='concevoir_poc' AND path='relances'"
            ).fetchone()[0],
            c.execute(
                'SELECT COUNT(*) FROM invocation_write_values v'
                ' JOIN invocation_writes w ON w.id=v.write_id'
                " WHERE w.invocation_id='concevoir_poc'"
                " AND v.column_name='followups'"
            ).fetchone()[0],
            c.execute(
                "SELECT COUNT(*) FROM tool_db_columns WHERE tool_id='plan_par_numero'"
                " AND column_name='followups'"
            ).fetchone()[0],
            'relances : leur rythme'
            in c.execute(
                "SELECT prompt FROM invocations WHERE id='concevoir_poc'"
            ).fetchone()[0],
        )

    def test_une_instance_de_la_pr4_perd_les_relances(self) -> None:
        c = self.conn
        avant = {ch['id']: ch for ch in self.changes}
        c.execute(
            'UPDATE invocations SET prompt=?, role=? WHERE id=?',
            (
                avant['lot10_plan_poc_sans_relances_prompt']['set']['prompt'][
                    'from'
                ].strip(),
                avant['lot10_plan_poc_sans_relances_role']['set']['role'][
                    'from'
                ].strip(),
                'concevoir_poc',
            ),
        )
        c.execute(
            'INSERT INTO invocation_output_fields(invocation_id, path, type,'
            " required, description, position) VALUES('concevoir_poc',"
            " 'relances', 'text', 1, 'Le rythme des relances.', 99)"
        )
        ecriture = c.execute(
            "SELECT id FROM invocation_writes WHERE invocation_id='concevoir_poc'"
            ' AND position=0'
        ).fetchone()[0]
        c.execute(
            'INSERT INTO invocation_write_values(write_id, column_name,'
            " source, value) VALUES(?, 'followups', 'field', 'relances')",
            (ecriture,),
        )
        c.execute(
            'INSERT INTO tool_db_columns(tool_id, table_name, column_name,'
            " output_name, position) VALUES('plan_par_numero', 'product_plans',"
            " 'followups', 'relances', 99)"
        )
        c.executemany(
            'DELETE FROM pipeline_changes WHERE id=?', [(i,) for i in self.IDS]
        )
        self.assertEqual(self._etat(), (1, 1, 1, True))
        apply_changes(c, self.changes)
        self.assertEqual(self._etat(), (0, 0, 0, False))
        self.assertEqual(
            c.execute(
                'SELECT result FROM pipeline_changes'
                " WHERE id='lot10_plan_poc_sans_relances_reponse'"
            ).fetchone()[0],
            'relances retiré',
        )

    def test_une_instance_neuve_n_a_rien_a_retirer(self) -> None:
        self.assertEqual(self._etat(), (0, 0, 0, False))
        resultats = dict(
            self.conn.execute(
                'SELECT id, result FROM pipeline_changes WHERE id IN'
                f' ({",".join("?" * len(self.IDS))})',
                self.IDS,
            ).fetchall()
        )
        self.assertEqual(
            resultats['lot10_plan_poc_sans_relances_ecriture'],
            'followups déjà absent',
        )
        # Le lot 11 a changé ce prompt depuis : une instance neuve a déjà le
        # dernier, et le changement du lot 10 n'y touche pas.
        self.assertNotIn(
            'modifié', resultats['lot10_plan_poc_sans_relances_prompt']
        )


class RegistrarCloudflareTests(unittest.TestCase):
    """Une instance de la PR 7 du lot 10 : Hostinger, et la carte en
    fichiers en clair. Au démarrage, elle passe à Cloudflare et à la carte
    chiffrée du coffre."""

    IDS = (
        'lot10_achat_cloudflare_prompt',
        'lot10_achat_cloudflare_outils',
        'lot10_conception_cloudflare',
        'lot10_paiement_carte_du_coffre_prompt',
        'lot10_paiement_carte_du_coffre_secrets',
        'lot10_domaine_commun_lien',
        'lot10_domaine_commun_vente',
        'lot10_domaine_commun_prod',
    )

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.data = read_yaml_file(config_dir() / 'pipeline.yaml')
        self.changes = {c['id']: c for c in self.data['changes']}

    def _secrets(self) -> str:
        return str(
            self.conn.execute(
                'SELECT p.value FROM invocation_tool_params p'
                ' JOIN invocation_tools t ON t.id=p.invocation_tool_id'
                " WHERE t.invocation_id='paiement_test'"
                " AND t.tool_id='navigateur_agir' AND p.param_name='secrets'"
            ).fetchone()[0]
        )

    def _comme_la_pr7(self, secrets: str) -> None:
        c = self.conn
        avant = self.changes
        navigateur_sans_ecran(c)
        c.execute(
            "UPDATE invocations SET prompt=? WHERE id='acheter_domaine'",
            (avant['lot10_achat_cloudflare_prompt']['set']['prompt']['from'],),
        )
        c.execute(
            "UPDATE invocations SET prompt=? WHERE id='paiement_test'",
            (
                avant['lot10_paiement_carte_du_coffre_prompt']['set'][
                    'prompt'
                ]['from'],
            ),
        )
        c.execute(
            'DELETE FROM invocation_tools WHERE tool_id LIKE ?'
            " AND invocation_id IN ('acheter_domaine', 'concevoir_produit')",
            ('cloudflare%',),
        )
        c.execute(
            'UPDATE invocation_tool_params SET value=? WHERE param_name='
            "'secrets' AND invocation_tool_id IN (SELECT id FROM"
            " invocation_tools WHERE invocation_id='paiement_test')",
            (secrets,),
        )
        c.execute(
            "INSERT INTO api_services(id, base_url) VALUES('hostinger',"
            " 'https://developers.hostinger.com')"
        )
        c.execute(
            'INSERT INTO tools(id, capability_id, titre) VALUES('
            "'hostinger_acheter_domaine', 'call_api', 'Acheter')"
        )
        c.execute(
            'INSERT INTO api_endpoints(tool_id, service_id, method, path)'
            " VALUES('hostinger_acheter_domaine', 'hostinger', 'POST',"
            " '/api/domains/v1/portfolio')"
        )
        c.execute(
            'INSERT INTO invocation_tools(invocation_id, tool_id, mode,'
            " position) VALUES('acheter_domaine', 'hostinger_acheter_domaine',"
            " 'callable', 99)"
        )
        # Avant le domaine commun : l'essai validé menait droit à l'achat.
        c.execute(
            "UPDATE links SET to_invocation_id='acheter_domaine', title=?"
            " WHERE id='test_produit_valide_vers_domaine'",
            ('Le produit essayé et validé ; Serge achète son domaine',),
        )
        c.execute(
            "DELETE FROM link_params WHERE link_id='vente_vers_prod'"
            " AND param_name='domaine_commun'"
        )
        c.execute(
            'DELETE FROM invocation_tool_params WHERE invocation_id='
            "'publier_prod_produit' AND param_name='base_domain'"
        )
        c.executemany(
            'DELETE FROM pipeline_changes WHERE id=?', [(i,) for i in self.IDS]
        )

    def test_une_instance_de_la_pr7_passe_a_cloudflare(self) -> None:
        anciens = self.changes['lot10_paiement_carte_du_coffre_secrets'][
            'set_tool_params'
        ]['secrets']
        self._comme_la_pr7(anciens['from'])
        seed_pipeline(self.conn, self.data)
        outils = [
            r[0]
            for r in self.conn.execute(
                'SELECT tool_id FROM invocation_tools'
                " WHERE invocation_id='acheter_domaine' ORDER BY position"
            )
        ]
        self.assertNotIn('hostinger_acheter_domaine', outils)
        self.assertIn('cloudflare_acheter_domaine', outils)
        self.assertIn('cloudflare_dns_creer', outils)
        self.assertTrue(
            self.conn.execute(
                'SELECT 1 FROM invocation_tools WHERE invocation_id='
                "'concevoir_produit' AND tool_id='cloudflare_disponibilite'"
            ).fetchone()
        )
        self.assertIn(
            'Cloudflare',
            self.conn.execute(
                "SELECT prompt FROM invocations WHERE id='acheter_domaine'"
            ).fetchone()[0],
        )
        self.assertIn(
            'payment-card.enc#pan',
            self.conn.execute(
                "SELECT prompt FROM invocations WHERE id='paiement_test'"
            ).fetchone()[0],
        )
        self.assertEqual(self._secrets(), anciens['to'])
        # L'essai validé passe d'abord par le choix du domaine, et le
        # domaine commun va jusqu'à la prod.
        self.assertEqual(
            self.conn.execute(
                'SELECT to_invocation_id FROM links'
                " WHERE id='test_produit_valide_vers_domaine'"
            ).fetchone()[0],
            'choisir_domaine',
        )
        self.assertTrue(
            self.conn.execute(
                "SELECT 1 FROM link_params WHERE link_id='vente_vers_prod'"
                " AND param_name='domaine_commun'"
            ).fetchone()
        )
        self.assertTrue(
            self.conn.execute(
                'SELECT 1 FROM invocation_tool_params WHERE invocation_id='
                "'publier_prod_produit' AND param_name='base_domain'"
            ).fetchone()
        )
        # Hostinger disparaît, sa description d'API comprise.
        for table, colonne in (
            ('api_services', 'id'),
            ('api_endpoints', 'service_id'),
        ):
            self.assertIsNone(
                self.conn.execute(
                    f"SELECT 1 FROM {table} WHERE {colonne}='hostinger'"
                ).fetchone()
            )

    def test_des_secrets_changes_dans_mission_control_sont_gardes(
        self,
    ) -> None:
        self._comme_la_pr7('mon-secret.key')
        seed_pipeline(self.conn, self.data)
        self.assertEqual(self._secrets(), 'mon-secret.key')
        self.assertIn(
            'gardé',
            self.conn.execute(
                'SELECT result FROM pipeline_changes WHERE id='
                "'lot10_paiement_carte_du_coffre_secrets'"
            ).fetchone()[0],
        )


class InstanceDuLot11Tests(unittest.TestCase):
    """Une instance du lot 11, telle qu'elle tourne : le plan d'un POC
    porte un nombre de prospects et un canal choisi dans une liste écrite
    d'avance, rien n'a de couloir ni de valeur d'essai, et les boutons
    d'essai de la page Système existent. Au démarrage, elle reçoit le
    lot 12 (Q98, Q99)."""

    def setUp(self) -> None:
        from tests.boutons_d_essai import poser

        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.data = read_yaml_file(config_dir() / 'pipeline.yaml')
        changes = {c['id']: c for c in self.data['changes']}
        c = self.conn
        # La conception du POC, comme au lot 11.
        prompt = c.execute(
            "SELECT prompt FROM invocations WHERE id='concevoir_poc'"
        ).fetchone()[0]
        for r in changes['lot12_poc_canal_branche']['set']['prompt'][
            'replace'
        ]:
            self.assertIn(r['new'], prompt)
            prompt = prompt.replace(r['new'], r['old'])
        c.execute(
            "UPDATE invocations SET prompt=? WHERE id='concevoir_poc'",
            (prompt,),
        )
        ecritures = [
            r[0]
            for r in c.execute(
                'SELECT id FROM invocation_writes WHERE invocation_id='
                "'concevoir_poc' ORDER BY position"
            )
        ]
        c.executescript(
            f"""
            UPDATE invocation_output_fields SET type='choice',
                choices='email, voice'
                WHERE invocation_id='concevoir_poc' AND path='canal';
            INSERT INTO invocation_output_fields(invocation_id, path, type,
                required, description, position)
                VALUES('concevoir_poc', 'prospects', 'number', 1, '', 99);
            INSERT INTO invocation_write_values(write_id, column_name,
                source, value) VALUES({ecritures[0]}, 'prospects', 'field',
                'prospects'), ({ecritures[6]}, 'n_target', 'field',
                'prospects');
            INSERT INTO invocation_settings(invocation_id, name, value)
                VALUES('concevoir_poc', 'prospects_min', '30'),
                ('concevoir_poc', 'prospects_max', '50');
            DELETE FROM invocation_tools WHERE invocation_id='concevoir_poc'
                AND tool_id='canaux_branches';
            INSERT INTO tool_db_columns(tool_id, table_name, column_name)
                VALUES('plan_par_numero', 'product_plans', 'prospects');
            UPDATE invocation_output_fields SET required=0, min_items=''
                WHERE invocation_id='choisir_business' AND path='choix';
            UPDATE invocation_settings SET trial_value='';
            DELETE FROM invocation_settings
                WHERE invocation_id='choisir_business' AND name='choix_min';
            UPDATE table_quotas SET where_column='', where_value=''
                WHERE id='cycles_ouverts';
            UPDATE links SET lane='';
            UPDATE invocations
                SET title='Essayer le captcha avec un humain (temporaire)'
                WHERE id='essayer_captcha';
            DELETE FROM pipeline_changes WHERE id LIKE 'lot12_%';
            """
        )
        c.execute(
            "UPDATE invocations SET role=? WHERE id='essayer_captcha'",
            (changes['lot12_captcha_dans_l_essai']['set']['role']['from'],),
        )
        # Les boutons d'essai des briques, encore là au lot 11.
        poser(c)

    def _un(self, sql: str) -> tuple:
        return tuple(self.conn.execute(sql).fetchone())

    def test_elle_recoit_le_lot_12(self) -> None:
        seed_pipeline(self.conn, self.data)
        c = self.conn
        # Le plan d'un POC : plus de nombre de prospects, un canal branché.
        prompt = self._un(
            "SELECT prompt FROM invocations WHERE id='concevoir_poc'"
        )[0]
        self.assertNotIn('prospects_min', prompt)
        self.assertIn('parmi les canaux branchés', prompt)
        champs = dict(
            c.execute(
                'SELECT path, type FROM invocation_output_fields'
                " WHERE invocation_id='concevoir_poc'"
            )
        )
        self.assertNotIn('prospects', champs)
        self.assertEqual(champs['canal'], 'text')
        self.assertEqual(
            self._un(
                'SELECT COUNT(*) FROM invocation_write_values v'
                ' JOIN invocation_writes w ON w.id=v.write_id'
                " WHERE w.invocation_id='concevoir_poc'"
                " AND v.column_name IN ('prospects', 'n_target')"
            ),
            (0,),
        )
        self.assertEqual(
            self._un(
                'SELECT COUNT(*) FROM invocation_settings WHERE invocation_id='
                "'concevoir_poc' AND name LIKE 'prospects_%'"
            ),
            (0,),
        )
        self.assertEqual(
            self._un(
                'SELECT mode FROM invocation_tools WHERE invocation_id='
                "'concevoir_poc' AND tool_id='canaux_branches'"
            ),
            ('given',),
        )
        self.assertEqual(
            self._un(
                'SELECT COUNT(*) FROM tool_db_columns WHERE tool_id='
                "'plan_par_numero' AND column_name='prospects'"
            ),
            (0,),
        )
        # Le couloir d'essai : les valeurs d'essai, les liens du vrai
        # pipeline, le cycle d'écoute d'un essai à part.
        essais = dict(
            (f'{i}.{n}', v)
            for i, n, v in c.execute(
                'SELECT invocation_id, name, trial_value'
                " FROM invocation_settings WHERE trial_value<>''"
                " AND invocation_id IN ('explorer_web', 'formuler_a',"
                " 'formuler_b', 'choisir_business')"
            )
        )
        self.assertEqual(
            essais,
            {
                'explorer_web.recherches_max': '2',
                'explorer_web.pages_max': '5',
                'explorer_web.flux_max': '0',
                'formuler_a.nombre_idees': '0',
                'formuler_b.nombre_idees': '0',
                'choisir_business.choix_min': '1',
            },
        )
        self.assertEqual(
            self._un(
                'SELECT required, min_items FROM invocation_output_fields'
                " WHERE invocation_id='choisir_business' AND path='choix'"
            ),
            (1, 'choix_min'),
        )
        self.assertEqual(
            sorted(
                r[0]
                for r in c.execute("SELECT id FROM links WHERE lane='real'")
            ),
            [
                'choix_vers_conception_poc',
                'domaine_a_acheter',
                'paiement_test_vers_produit_pret',
            ],
        )
        self.assertEqual(
            self._un(
                'SELECT where_column, where_value FROM table_quotas'
                " WHERE id='cycles_ouverts'"
            ),
            ('trial', '0'),
        )
        # Les essais de la page Système sont retirés ; le captcha reste,
        # comme étape de l'essai total.
        self.assertEqual(
            sorted(
                r[0]
                for r in c.execute(
                    "SELECT id FROM triggers WHERE event='button'"
                    " AND deleted_at='' AND id LIKE 'bouton_ess%'"
                )
            ),
            ['bouton_essai_total'],
        )
        self.assertEqual(
            self._un(
                'SELECT COUNT(*) FROM invocations WHERE id IN'
                " ('essayer_chantier', 'essayer_navigateur', 'publier_essai',"
                " 'essayer_stripe', 'creer_business_essai',"
                " 'bout_en_bout_produit') AND deleted_at=''"
            ),
            (0,),
        )
        titre, role, supprime = self._un(
            'SELECT title, role, deleted_at FROM invocations'
            " WHERE id='essayer_captcha'"
        )
        self.assertEqual(titre, 'Essayer le captcha avec un humain')
        self.assertIn('essai total', role)
        self.assertEqual(supprime, '')

    def test_la_base_du_lot_11_renomme_la_phase_des_campagnes(self) -> None:
        from serge.db.migrate import MIGRATIONS, apply_pending

        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        apply_pending(conn, [m for m in MIGRATIONS if m[0] <= 52], head=52)
        conn.executescript(
            """
            INSERT INTO campaigns(id, venture_id, family, channel, state,
                n_target, created_at, updated_at)
                VALUES('c1', 'v1', 'test_leger', 'email', 'DRAFT', 30, 't', 't');
            INSERT INTO writable_columns(table_name, column_name)
                VALUES('campaigns', 'family');
            INSERT INTO invocation_writes(id, invocation_id, table_name,
                operation) VALUES(7, 'concevoir_poc', 'campaigns', 'insert');
            INSERT INTO invocation_write_values(write_id, column_name, source,
                value) VALUES(7, 'family', 'fixed', 'test_leger');
            """
        )
        apply_pending(conn, MIGRATIONS)
        self.assertEqual(
            tuple(
                conn.execute(
                    'SELECT phase, n_target FROM campaigns'
                ).fetchone()
            ),
            ('smoke', 30),
        )
        self.assertEqual(
            tuple(
                conn.execute(
                    'SELECT column_name, value FROM invocation_write_values'
                ).fetchone()
            ),
            ('phase', 'smoke'),
        )
        self.assertEqual(
            conn.execute(
                "SELECT column_name FROM writable_columns WHERE table_name='campaigns'"
            ).fetchall(),
            [('phase',)],
        )


if __name__ == '__main__':
    unittest.main()


class InstanceDuLot10Tests(unittest.TestCase):
    """Le serveur tel que le lot 10 l'a laissé : les constructeurs essaient
    dans le navigateur avec Opus, les relecteurs n'ont pas de boîte e-mail.
    Au démarrage, il reçoit les changements du lot 11 (Q96)."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        self.lot11 = [
            c for c in data['changes'] if c['id'].startswith('lot11_')
        ]
        self.yaml = {i['id']: i for i in data['invocations']}
        c = self.conn
        for change in self.lot11:
            regles = change.get('set') or {}
            inv = (change.get('where') or {}).get('id')
            if 'prompt' in regles:
                texte = c.execute(
                    'SELECT prompt FROM invocations WHERE id=?', (inv,)
                ).fetchone()[0]
                for pair in regles['prompt']['replace']:
                    texte = texte.replace(
                        pair['new'].strip(), pair['old'].strip(), 1
                    )
                c.execute(
                    'UPDATE invocations SET prompt=? WHERE id=?', (texte, inv)
                )
            if 'role' in regles:
                c.execute(
                    'UPDATE invocations SET role=? WHERE id=?',
                    (regles['role']['from'], inv),
                )
            if 'model_tier' in regles:
                c.execute(
                    "UPDATE invocations SET model_tier='code' WHERE id=?",
                    (inv,),
                )
        for inv in ('construire_poc', 'construire_produit'):
            for position, outil in enumerate(
                ('navigateur_agir', 'navigateur_lire', 'navigateur_capture'),
                50,
            ):
                c.execute(
                    'INSERT INTO invocation_tools(invocation_id, tool_id,'
                    " mode, position) VALUES(?, ?, 'callable', ?)",
                    (inv, outil, position),
                )
        c.execute(
            'DELETE FROM invocation_tools WHERE tool_id IN (?,?,?,?)',
            (
                'boite_mail',
                'stripe_chercher_clients',
                'stripe_abonnements',
                'stripe_annuler_abonnement',
            ),
        )
        c.execute("DELETE FROM pipeline_changes WHERE id LIKE 'lot11_%'")

    def _outils(self, inv: str) -> list[str]:
        return [
            str(r[0])
            for r in self.conn.execute(
                'SELECT tool_id FROM invocation_tools WHERE invocation_id=?'
                ' ORDER BY position',
                (inv,),
            )
        ]

    def test_elle_recoit_le_lot_11(self) -> None:
        ensure_pipeline(self.conn)
        for change in self.lot11:
            inv = (change.get('where') or {}).get('id')
            if not inv:
                continue
            prompt, tier = self.conn.execute(
                'SELECT prompt, model_tier FROM invocations WHERE id=?',
                (inv,),
            ).fetchone()
            self.assertEqual(prompt, self.yaml[inv]['prompt'].strip(), inv)
            self.assertEqual(tier, self.yaml[inv]['model_tier'], inv)
        for inv in ('construire_poc', 'construire_produit'):
            self.assertFalse(
                [o for o in self._outils(inv) if o.startswith('navigateur')]
            )
        self.assertIn('boite_mail', self._outils('relire_poc'))
        self.assertIn(
            'stripe_annuler_abonnement', self._outils('relire_produit')
        )
        self.assertIn('boite_mail', self._outils('paiement_test'))
        self.assertEqual(
            self.conn.execute(
                "SELECT model FROM llm_models WHERE tier='web'"
            ).fetchone()[0],
            'anthropic/claude-sonnet-5.5',
        )

    def test_un_prompt_change_a_la_main_garde_ses_changements(self) -> None:
        self.conn.execute(
            'UPDATE invocations SET prompt=prompt || ? WHERE id=?',
            ('\nJulien : sois bref.', 'construire_produit'),
        )
        self.conn.execute(
            "UPDATE invocations SET prompt=replace(prompt, 'Règles :',"
            " 'Les règles :') WHERE id='construire_produit'"
        )
        ensure_pipeline(self.conn)
        prompt = self.conn.execute(
            "SELECT prompt FROM invocations WHERE id='construire_produit'"
        ).fetchone()[0]
        self.assertIn('Julien : sois bref.', prompt)
        self.assertIn('n’essaie pas le produit'.replace('’', "'"), prompt)
        self.assertNotIn('SMTP_HOST', prompt)
        resultat = self.conn.execute(
            "SELECT result FROM pipeline_changes WHERE id='lot11_construire_produit'"
        ).fetchone()[0]
        self.assertIn('2 passage(s) remplacé(s), 1 gardé(s)', resultat)


def navigateur_sans_ecran(conn: sqlite3.Connection) -> None:
    """Le paiement test d'avant le vrai Chrome (Q97)."""
    conn.execute(
        "UPDATE invocation_tools SET tool_id=replace(tool_id, 'vrai_chrome_',"
        " 'navigateur_') WHERE invocation_id='paiement_test'"
        " AND tool_id LIKE 'vrai_chrome_%'"
    )
    conn.execute(
        "DELETE FROM invocation_tools WHERE invocation_id='paiement_test'"
        " AND tool_id='appeler_un_humain'"
    )


class VraiChromeTests(unittest.TestCase):
    """Une instance du lot 11 : le paiement test paie dans le navigateur
    sans écran, avec le niveau « web » sur Haiku. Au démarrage, il passe au
    vrai Chrome, peut appeler un humain, et le niveau repasse à Sonnet
    (Q97)."""

    IDS = (
        'vrai_chrome_paiement_test_sans_navigateur',
        'vrai_chrome_paiement_test_outils',
        'vrai_chrome_paiement_test_consignes',
        'vrai_chrome_niveau_web_sonnet',
    )

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.data = read_yaml_file(config_dir() / 'pipeline.yaml')
        consignes = {c['id']: c for c in self.data['changes']}[self.IDS[2]]
        c = self.conn
        navigateur_sans_ecran(c)
        prompt = c.execute(
            "SELECT prompt FROM invocations WHERE id='paiement_test'"
        ).fetchone()[0]
        for remplacement in consignes['set']['prompt']['replace']:
            prompt = prompt.replace(remplacement['new'], remplacement['old'])
        c.execute(
            "UPDATE invocations SET prompt=? WHERE id='paiement_test'",
            (prompt,),
        )
        c.execute(
            "UPDATE llm_models SET model='anthropic/claude-haiku-5.5'"
            " WHERE tier='web'"
        )
        c.executemany(
            'DELETE FROM pipeline_changes WHERE id=?', [(i,) for i in self.IDS]
        )

    def test_le_paiement_test_passe_au_vrai_chrome(self) -> None:
        self.assertNotIn(
            'captcha',
            self.conn.execute(
                "SELECT prompt FROM invocations WHERE id='paiement_test'"
            ).fetchone()[0],
        )
        seed_pipeline(self.conn, self.data)
        outils = {
            str(r[0])
            for r in self.conn.execute(
                'SELECT tool_id FROM invocation_tools'
                " WHERE invocation_id='paiement_test'"
            )
        }
        self.assertLessEqual(
            {
                'vrai_chrome_agir',
                'vrai_chrome_lire',
                'vrai_chrome_capture',
                'appeler_un_humain',
            },
            outils,
        )
        self.assertFalse({o for o in outils if o.startswith('navigateur_')})
        secrets = self.conn.execute(
            'SELECT p.value FROM invocation_tool_params p'
            ' JOIN invocation_tools t ON t.id=p.invocation_tool_id'
            " WHERE t.invocation_id='paiement_test'"
            " AND t.tool_id='vrai_chrome_agir' AND p.param_name='secrets'"
        ).fetchone()[0]
        self.assertIn('payment-card.enc#pan', secrets)
        prompt = self.conn.execute(
            "SELECT prompt FROM invocations WHERE id='paiement_test'"
        ).fetchone()[0]
        self.assertIn('Ouvre le lien dans le vrai Chrome', prompt)
        self.assertIn('appelle « Appeler un humain »', prompt)
        self.assertEqual(
            self.conn.execute(
                "SELECT model FROM llm_models WHERE tier='web'"
            ).fetchone()[0],
            'anthropic/claude-sonnet-5.5',
        )


class InstanceDuLot12Tests(unittest.TestCase):
    """Le serveur du 17 novembre 2026 : le lien qui rouvre le ticket
    « Choix du principal » passait après chaque réponse, même « Valider »."""

    def test_le_choix_n_est_redemande_que_pour_un_nom_inconnu(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        conn.executescript(
            """
            UPDATE links SET condition_field='choice_id',
                condition_op='non_vide', condition_value=''
                WHERE id='choix_a_redemander';
            DELETE FROM pipeline_changes
                WHERE id='lot12_choix_redemande_si_nom_inconnu';
            """
        )
        seed_pipeline(conn, read_yaml_file(config_dir() / 'pipeline.yaml'))
        self.assertEqual(
            tuple(
                conn.execute(
                    'SELECT condition_field, condition_op, condition_value'
                    " FROM links WHERE id='choix_a_redemander'"
                ).fetchone()
            ),
            ('redemander', '=', 'oui'),
        )


class StripeParCleTests(unittest.TestCase):
    """Le serveur du 19 novembre 2026 : le paiement test cherchait le
    produit par la recherche de Stripe, 9 secondes après sa mise en vente,
    et ne le trouvait pas. Au démarrage, il le retrouve par la clé de
    recherche de son prix, et la mise en vente regarde aussi cette clé."""

    IDS = (
        'lot13_paiement_test_par_cle',
        'lot13_paiement_test_sans_recherche',
        'lot13_paiement_test_consigne',
        'lot13_vendre_test_par_cle',
        'lot13_vendre_par_cle',
        'lot13_vendre_test_consigne',
        'lot13_vendre_consigne',
    )
    CONSIGNES = {
        'paiement_test': 'lot13_paiement_test_consigne',
        'vendre_en_mode_test': 'lot13_vendre_test_consigne',
        'mettre_en_vente': 'lot13_vendre_consigne',
    }

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.data = read_yaml_file(config_dir() / 'pipeline.yaml')
        changements = {c['id']: c for c in self.data['changes']}
        c = self.conn
        # L'instance d'avant : pas de clé, la recherche partout.
        c.execute(
            'DELETE FROM invocation_tool_params WHERE invocation_tool_id IN'
            " (SELECT id FROM invocation_tools WHERE tool_id='stripe_prix_par_cle')"
            " AND param_name IN ('lookup_keys[0]', 'active')"
        )
        c.execute(
            "UPDATE invocation_tools SET tool_id='stripe_chercher_produits'"
            " WHERE invocation_id='paiement_test'"
            " AND tool_id='stripe_prix_par_cle'"
        )
        c.execute(
            'DELETE FROM invocation_tool_params WHERE invocation_tool_id IN'
            " (SELECT id FROM invocation_tools WHERE tool_id='stripe_prix_par_cle')"
        )
        c.execute(
            "DELETE FROM invocation_tools WHERE tool_id='stripe_prix_par_cle'"
        )
        for invocation, ident in self.CONSIGNES.items():
            prompt = c.execute(
                'SELECT prompt FROM invocations WHERE id=?', (invocation,)
            ).fetchone()[0]
            for passage in changements[ident]['set']['prompt']['replace']:
                self.assertIn(passage['new'], prompt)
                prompt = prompt.replace(passage['new'], passage['old'])
            c.execute(
                'UPDATE invocations SET prompt=? WHERE id=?',
                (prompt, invocation),
            )
        c.executemany(
            'DELETE FROM pipeline_changes WHERE id=?', [(i,) for i in self.IDS]
        )

    def _outils(self, invocation: str) -> list[str]:
        return [
            str(r[0])
            for r in self.conn.execute(
                'SELECT tool_id FROM invocation_tools WHERE invocation_id=?',
                (invocation,),
            )
        ]

    def test_le_produit_se_retrouve_par_la_cle_de_son_prix(self) -> None:
        self.assertNotIn('stripe_prix_par_cle', self._outils('paiement_test'))
        seed_pipeline(self.conn, self.data)
        paiement = self._outils('paiement_test')
        self.assertIn('stripe_prix_par_cle', paiement)
        self.assertNotIn('stripe_chercher_produits', paiement)
        for invocation in ('vendre_en_mode_test', 'mettre_en_vente'):
            outils = self._outils(invocation)
            self.assertIn('stripe_prix_par_cle', outils)
            self.assertIn('stripe_chercher_produits', outils)
        # La clé est le numéro du business, figé en base : le modèle ne la
        # choisit pas. Le mode de Stripe suit l'invocation.
        figes = {
            (str(r[0]), str(r[1])): (str(r[2]), str(r[3]))
            for r in self.conn.execute(
                'SELECT t.invocation_id, p.param_name, p.source, p.value'
                ' FROM invocation_tool_params p'
                ' JOIN invocation_tools t ON t.id=p.invocation_tool_id'
                " WHERE t.tool_id='stripe_prix_par_cle'"
            )
        }
        for invocation, service in (
            ('paiement_test', 'stripe_live'),
            ('mettre_en_vente', 'stripe_live'),
            ('vendre_en_mode_test', 'stripe_test'),
        ):
            self.assertEqual(
                figes[invocation, 'lookup_keys[0]'], ('task', 'venture_id')
            )
            self.assertEqual(figes[invocation, 'active'], ('fixed', 'true'))
            self.assertEqual(figes[invocation, 'service'], ('fixed', service))
        for invocation in self.CONSIGNES:
            prompt = self.conn.execute(
                'SELECT prompt FROM invocations WHERE id=?', (invocation,)
            ).fetchone()[0]
            self.assertIn(
                'Trouver un prix\n   Stripe par sa clé de recherche'
                if invocation == 'paiement_test'
                else '« Trouver un prix Stripe par sa clé de recherche »',
                prompt,
            )
        self.assertNotIn(
            "(recherche :\n   metadata['venture_id']",
            self.conn.execute(
                "SELECT prompt FROM invocations WHERE id='paiement_test'"
            ).fetchone()[0],
        )


class FouillesDesReseauxTests(unittest.TestCase):
    """Une instance du lot 12 : « Explorer le web » ne sait que chercher
    et lire un aperçu. Au démarrage, elle peut confier une fouille de
    Reddit, d'Instagram ou de X, et sa consigne dit quand (Q104)."""

    IDS = (
        'lot13_explorer_fouille_les_reseaux',
        'lot13_explorer_consigne_des_reseaux',
    )

    def test_explorer_recoit_les_fouilles(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        consigne = {c['id']: c for c in data['changes']}[self.IDS[1]]
        prompt = conn.execute(
            "SELECT prompt FROM invocations WHERE id='explorer_web'"
        ).fetchone()[0]
        for passage in consigne['set']['prompt']['replace']:
            self.assertIn(passage['new'], prompt)
            prompt = prompt.replace(passage['new'], passage['old'])
        conn.execute(
            "UPDATE invocations SET prompt=? WHERE id='explorer_web'",
            (prompt,),
        )
        conn.execute(
            'DELETE FROM invocation_tool_params WHERE invocation_tool_id IN'
            " (SELECT id FROM invocation_tools WHERE tool_id LIKE 'fouiller_%')"
        )
        conn.execute(
            "DELETE FROM invocation_tools WHERE tool_id LIKE 'fouiller_%'"
        )
        conn.executemany(
            'DELETE FROM pipeline_changes WHERE id=?', [(i,) for i in self.IDS]
        )
        seed_pipeline(conn, data)
        figes = {
            (str(r[0]), str(r[1])): (str(r[2]), str(r[3]), str(r[4]))
            for r in conn.execute(
                'SELECT t.tool_id, p.param_name, p.source, p.value,'
                ' t.max_calls FROM invocation_tool_params p'
                ' JOIN invocation_tools t ON t.id=p.invocation_tool_id'
                " WHERE t.invocation_id='explorer_web'"
                " AND t.tool_id LIKE 'fouiller_%'"
            )
        }
        for reseau in ('reddit', 'instagram', 'x'):
            outil = f'fouiller_{reseau}'
            self.assertEqual(
                figes[outil, 'invocation'],
                ('fixed', 'fouiller_reseau', 'fouilles_par_reseau'),
            )
            self.assertEqual(figes[outil, 'account'][:2], ('fixed', reseau))
            self.assertEqual(figes[outil, 'task_id'][:2], ('task', 'task_id'))
        self.assertIn(
            'au\n  plus {fouilles_par_reseau} fois par réseau',
            conn.execute(
                "SELECT prompt FROM invocations WHERE id='explorer_web'"
            ).fetchone()[0],
        )


class CanauxDuNavigateurTests(unittest.TestCase):
    """Une instance du lot 12 : la relève toutes les 2 minutes prend tout
    canal qui se relève, et « Trouver des prospects » ne connaît que
    l'e-mail et le téléphone. Au démarrage, la relève rapide ne prend plus
    que les canaux rapides, et la recherche de prospects sait ce qu'est un
    profil (Q104)."""

    IDS = (
        'lot13_releve_rapide_par_rythme',
        'lot13_prospects_fouille_les_reseaux',
        'lot13_prospects_consigne_des_profils',
    )

    def test_elle_recoit_les_canaux_du_navigateur(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        consigne = {c['id']: c for c in data['changes']}[self.IDS[2]]
        prompt = conn.execute(
            "SELECT prompt FROM invocations WHERE id='trouver_prospects'"
        ).fetchone()[0]
        for passage in consigne['set']['prompt']['replace']:
            self.assertIn(passage['new'], prompt)
            prompt = prompt.replace(passage['new'], passage['old'])
        conn.execute(
            "UPDATE invocations SET prompt=? WHERE id='trouver_prospects'",
            (prompt,),
        )
        conn.executescript(
            """
            UPDATE triggers SET filter_column='polls', filter_value='1'
                WHERE id='releve_des_canaux';
            DELETE FROM invocation_tool_params WHERE invocation_tool_id IN
                (SELECT id FROM invocation_tools
                 WHERE invocation_id='trouver_prospects'
                 AND tool_id LIKE 'fouiller_%');
            DELETE FROM invocation_tools
                WHERE invocation_id='trouver_prospects'
                AND tool_id LIKE 'fouiller_%';
            """
        )
        conn.executemany(
            'DELETE FROM pipeline_changes WHERE id=?', [(i,) for i in self.IDS]
        )
        seed_pipeline(conn, data)
        self.assertEqual(
            {
                str(r[0]): (str(r[1]), str(r[2]), int(r[3]))
                for r in conn.execute(
                    'SELECT id, filter_column, filter_value, every_minutes'
                    " FROM triggers WHERE id LIKE 'releve_des_%'"
                )
            },
            {
                'releve_des_canaux': ('poll_pace', 'fast', 2),
                'releve_des_messageries': ('poll_pace', 'slow', 240),
            },
        )
        outils = [
            str(r[0])
            for r in conn.execute(
                'SELECT tool_id FROM invocation_tools'
                " WHERE invocation_id='trouver_prospects'"
            )
        ]
        for reseau in ('linkedin', 'instagram', 'x'):
            self.assertIn(f'fouiller_{reseau}', outils)
        self.assertIn(
            'canal linkedin, instagram ou x',
            conn.execute(
                "SELECT prompt FROM invocations WHERE id='trouver_prospects'"
            ).fetchone()[0],
        )


class CreationDeCompteTests(unittest.TestCase):
    """Le serveur du 20 novembre 2026 : le bouton « Créer un compte web »
    demande un « nom du compte » (le pseudo y a été tapé), ne demande pas
    le pseudo, et la consigne ne dit rien d'une identité incomplète."""

    IDS = (
        'lot13_compte_libelle_du_site',
        'lot13_compte_pseudo_du_bouton',
        'lot13_compte_pseudo_du_lien',
        'lot13_compte_consigne_du_pseudo',
    )
    ANCIEN = 'nom du compte, un mot (reddit, linkedin, x…)'

    def _bouton(self, conn: sqlite3.Connection) -> dict[str, str]:
        return {
            str(r[0]): str(r[1])
            for r in conn.execute(
                'SELECT param_name, value FROM trigger_params'
                " WHERE trigger_id='bouton_creer_compte_web'"
            )
        }

    def test_il_recoit_le_bouton_corrige(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        changes = {c['id']: c for c in data['changes']}
        prompt = conn.execute(
            "SELECT prompt FROM invocations WHERE id='creer_compte_web'"
        ).fetchone()[0]
        for passage in changes[self.IDS[3]]['set']['prompt']['replace']:
            self.assertIn(passage['new'], prompt)
            prompt = prompt.replace(passage['new'], passage['old'])
        conn.execute(
            "UPDATE invocations SET prompt=? WHERE id='creer_compte_web'",
            (prompt,),
        )
        conn.execute(
            'UPDATE trigger_params SET value=? WHERE'
            " trigger_id='bouton_creer_compte_web' AND param_name='compte'",
            (self.ANCIEN,),
        )
        conn.executescript(
            """
            DELETE FROM trigger_params WHERE param_name='pseudo'
                AND trigger_id='bouton_creer_compte_web';
            DELETE FROM link_params WHERE param_name='pseudo'
                AND link_id='compte_ouvert_vers_creation';
            """
        )
        conn.executemany(
            'DELETE FROM pipeline_changes WHERE id=?', [(i,) for i in self.IDS]
        )
        self.assertEqual(
            sorted(self._bouton(conn)), ['compte', 'lien', 'naissance']
        )
        seed_pipeline(conn, data)
        bouton = self._bouton(conn)
        self.assertEqual(
            bouton['compte'],
            'le site, en un mot : reddit, linkedin, instagram ou x'
            ' (pas le pseudo)',
        )
        self.assertIn('pseudo voulu sur ce site', bouton['pseudo'])
        self.assertEqual(
            tuple(
                conn.execute(
                    'SELECT source, value FROM link_params WHERE'
                    " link_id='compte_ouvert_vers_creation'"
                    " AND param_name='pseudo'"
                ).fetchone()
            ),
            ('task', 'pseudo'),
        )
        prompt = conn.execute(
            "SELECT prompt FROM invocations WHERE id='creer_compte_web'"
        ).fetchone()[0]
        self.assertIn('avec le pseudo voulu sur ce site', prompt)
        self.assertIn(
            "arrête-toi tout de suite, avant d'ouvrir le site", prompt
        )
        self.assertNotIn('ajoute « -ia »', prompt)

    def test_un_libelle_change_dans_mission_control_est_garde(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        conn.execute(
            "UPDATE trigger_params SET value='le site' WHERE"
            " trigger_id='bouton_creer_compte_web' AND param_name='compte'"
        )
        conn.execute('DELETE FROM pipeline_changes WHERE id=?', (self.IDS[0],))
        seed_pipeline(conn, read_yaml_file(config_dir() / 'pipeline.yaml'))
        self.assertEqual(self._bouton(conn)['compte'], 'le site')


class TelephoneEtPseudoTests(unittest.TestCase):
    """Le serveur du 20 novembre 2026, après l'inscription ratée sur X :
    « Créer un compte web » donne le téléphone d'office, et les essais de
    message demandent l'adresse d'un profil."""

    IDS = (
        'lot13_compte_telephone_si_exige',
        'lot13_essai_message_par_pseudo',
        'lot13_essai_lecture_par_pseudo',
        'lot13_envoi_web_par_pseudo',
        'lot13_lecture_web_par_pseudo',
        'lot13_compte_telephone_seule_voie',
        'lot13_compte_cite_les_erreurs',
    )
    # Ce qui manquait au serveur le 21 novembre 2026, après l'essai sur X.
    DU_21 = IDS[-2:]

    def _prompt(self, conn: sqlite3.Connection, invocation: str) -> str:
        return str(
            conn.execute(
                'SELECT prompt FROM invocations WHERE id=?', (invocation,)
            ).fetchone()[0]
        )

    def _libelles(self, conn: sqlite3.Connection) -> list[str]:
        return [
            str(r[0])
            for r in conn.execute(
                "SELECT value FROM trigger_params WHERE param_name='adresse'"
                ' AND trigger_id IN (?, ?) ORDER BY trigger_id',
                (
                    'bouton_lire_conversation_reseau',
                    'bouton_message_d_essai_reseau',
                ),
            )
        ]

    def _serveur(
        self, ids: tuple[str, ...] = ()
    ) -> tuple[sqlite3.Connection, dict, dict[str, str]]:
        """Une base comme celle du serveur avant ces modifications (toutes,
        ou seulement ``ids``), le fichier, et les consignes d'une instance
        neuve. Les modifications se défont de la dernière à la première."""
        ids = ids or self.IDS
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        changes = {c['id']: c for c in data['changes']}
        neuves: dict[str, str] = {}
        for ident in reversed(ids):
            change = changes[ident]
            where = change['where']
            if change['table'] == 'trigger_params':
                conn.execute(
                    'UPDATE trigger_params SET value=? WHERE trigger_id=?'
                    ' AND param_name=?',
                    (
                        change['set']['value']['from'],
                        where['trigger_id'],
                        where['param_name'],
                    ),
                )
                continue
            prompt = self._prompt(conn, where['id'])
            neuves.setdefault(where['id'], prompt)
            for passage in reversed(change['set']['prompt']['replace']):
                self.assertEqual(prompt.count(passage['new']), 1, ident)
                prompt = prompt.replace(passage['new'], passage['old'])
            conn.execute(
                'UPDATE invocations SET prompt=? WHERE id=?',
                (prompt, where['id']),
            )
        conn.executemany(
            'DELETE FROM pipeline_changes WHERE id=?', [(i,) for i in ids]
        )
        return conn, data, neuves

    def test_il_recoit_les_consignes_et_les_libelles(self) -> None:
        conn, data, neuves = self._serveur()
        avant = self._prompt(conn, 'creer_compte_web')
        self.assertIn('téléphone, donne celui des SMS.', avant)
        self.assertNotIn('keep', avant)
        self.assertIn(
            '1. Ouvre le profil de la personne (« adresse »).',
            self._prompt(conn, 'envoyer_par_le_web'),
        )
        self.assertEqual(
            self._libelles(conn),
            [
                'adresse du profil dont lire la réponse (https://…)',
                'adresse du profil à qui écrire (https://…)',
            ],
        )
        seed_pipeline(conn, data)
        # Les trois consignes sont, au caractère près, celles d'une
        # instance neuve.
        self.assertEqual(
            sorted(neuves),
            sorted(
                ['creer_compte_web', 'envoyer_par_le_web', 'lire_messagerie']
            ),
        )
        for invocation, neuve in neuves.items():
            self.assertEqual(self._prompt(conn, invocation), neuve)
        apres = neuves['creer_compte_web']
        self.assertIn("ne le donne que si le site l'exige", apres)
        self.assertIn("Un lien, tu l'ouvres dans le vrai Chrome", apres)
        self.assertIn('ne remplis pas le formulaire en boucle', apres)
        self.assertIn('par la recherche du site', neuves['envoyer_par_le_web'])
        self.assertIn(
            "se connecter à un compte qui existe, pas à s'inscrire", apres
        )
        for libelle in self._libelles(conn):
            self.assertIn('son pseudo sur ce réseau', libelle)
        # Une seconde fois ne change rien.
        seed_pipeline(conn, data)
        self.assertEqual(self._prompt(conn, 'creer_compte_web'), apres)

    def test_le_serveur_du_21_novembre_recoit_la_seule_voie(self) -> None:
        """Après les essais sur X du 21 novembre : les deux dernières
        modifications manquent au serveur."""
        conn, data, neuves = self._serveur(self.DU_21)
        avant = self._prompt(conn, 'creer_compte_web')
        self.assertIn("ne le donne que si le site l'exige", avant)
        self.assertNotIn('Trois précisions', avant)
        seed_pipeline(conn, data)
        apres = self._prompt(conn, 'creer_compte_web')
        self.assertEqual(apres, neuves['creer_compte_web'])
        self.assertIn("Quand l'inscription n'offre que le téléphone", apres)
        self.assertIn('le téléphone est exigé : donne celui des SMS', apres)
        self.assertIn('essaie-la', apres)
        self.assertIn('cite dans ton compte rendu', apres)
        for ident in self.DU_21:
            self.assertEqual(
                self._resultat(conn, ident),
                'prompt : 1 passage(s) remplacé(s)',
            )

    def _resultat(self, conn: sqlite3.Connection, ident: str) -> str:
        return str(
            conn.execute(
                'SELECT result FROM pipeline_changes WHERE id=?', (ident,)
            ).fetchone()[0]
        )

    def test_une_instance_neuve_n_est_pas_touchee(self) -> None:
        """Les modifications d'une même consigne s'enchaînent sans rien
        poser deux fois : une instance neuve a déjà le texte du fichier.
        (Un passage ajouté par une modification ne se réécrit pas dans la
        suivante : la première le reposerait.)"""
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        fichier = {i['id']: i.get('prompt') for i in data['invocations']}
        for invocation in (
            'creer_compte_web',
            'envoyer_par_le_web',
            'lire_messagerie',
        ):
            self.assertEqual(
                self._prompt(conn, invocation), fichier[invocation].strip()
            )
        self.assertEqual(
            self._prompt(conn, 'creer_compte_web').count(
                'Si un bouton ne fait rien'
            ),
            1,
        )
        for ident in (self.IDS[0], *self.IDS[3:]):
            self.assertEqual(
                self._resultat(conn, ident), 'prompt déjà à jour', ident
            )

    def test_une_consigne_changee_dans_mission_control_est_gardee(
        self,
    ) -> None:
        """Clem a réécrit la fin du paragraphe dans Mission Control : la
        modification du fichier ne trouve plus où se poser, et n'écrase
        rien."""
        conn, data, _ = self._serveur(self.DU_21)
        a_la_main = self._prompt(conn, 'creer_compte_web').replace(
            'décrivant ce que la page montre.', 'disant ce que tu vois.'
        )
        conn.execute(
            "UPDATE invocations SET prompt=? WHERE id='creer_compte_web'",
            (a_la_main,),
        )
        seed_pipeline(conn, data)
        self.assertEqual(self._prompt(conn, 'creer_compte_web'), a_la_main)
        for ident in self.DU_21:
            self.assertIn('gardé', self._resultat(conn, ident))

    def test_un_libelle_change_dans_mission_control_est_garde(self) -> None:
        conn, data, _ = self._serveur()
        conn.execute(
            "UPDATE trigger_params SET value='le profil' WHERE"
            " trigger_id='bouton_message_d_essai_reseau'"
            " AND param_name='adresse'"
        )
        seed_pipeline(conn, data)
        self.assertEqual(self._libelles(conn)[1], 'le profil')


class DemandeDeContactTests(unittest.TestCase):
    """Le serveur du 21 novembre 2026 au soir : la mission d'envoi par le
    navigateur ne sait qu'écrire ou renoncer. Il reçoit de quoi demander le
    contact et attendre (décision Q110) : la consigne, le rôle, la réponse
    « attente », le texte du bouton d'essai, et la boucle de l'essai."""

    IDS = (
        'lot13_envoi_web_demande_le_contact',
        'lot13_envoi_web_role_contact',
        'lot13_envoi_web_reponse_attente',
        'lot13_essai_message_attend_le_contact',
    )
    LIENS = ('essai_attend_un_contact', 'essai_retourne_voir')
    COMPTEUR = 'compter_rappels_contact'
    # Le compteur et les liens posés le 21 novembre, remplacés le 22.
    VIEUX_LIENS = ('essai_attend_le_contact', 'essai_rappele_apres_attente')
    VIEUX_COMPTEUR = 'compter_rappels_essai'

    def _etat(self, conn: sqlite3.Connection) -> dict[str, list]:
        """Tout ce que ces modifications touchent, tel qu'il est en base."""
        lus = {
            'mission': (
                'SELECT prompt, role FROM invocations WHERE id=?',
                ('envoyer_par_le_web',),
            ),
            'reponse': (
                'SELECT choices, description FROM invocation_output_fields'
                ' WHERE invocation_id=? AND path=?',
                ('envoyer_par_le_web', 'envoye'),
            ),
            'bouton': (
                'SELECT confirm_text FROM triggers WHERE id=?',
                ('bouton_message_d_essai_reseau',),
            ),
            'liens': (
                'SELECT id, from_invocation_id, to_invocation_id,'
                ' condition_field, condition_op, condition_value,'
                ' delay_min_setting, delay_max_setting FROM links'
                ' WHERE id IN (?, ?) ORDER BY id',
                self.LIENS,
            ),
            'parametres': (
                'SELECT link_id, param_name, source, value FROM link_params'
                ' WHERE link_id IN (?, ?) ORDER BY link_id, param_name',
                self.LIENS,
            ),
            'compteur': (
                'SELECT title, type, queue_id FROM invocations WHERE id=?',
                (self.COMPTEUR,),
            ),
            'tours': (
                'SELECT param_name, source, value FROM invocation_tool_params'
                ' WHERE invocation_id=? ORDER BY param_name',
                (self.COMPTEUR,),
            ),
        }
        return {
            nom: [tuple(r) for r in conn.execute(sql, args)]
            for nom, (sql, args) in lus.items()
        }

    def _serveur(self) -> tuple[sqlite3.Connection, dict, dict[str, list]]:
        """Une base comme celle du serveur avant ces modifications, le
        fichier, et l'état d'une instance neuve."""
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        neuf = self._etat(conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        changes = {c['id']: c for c in data['changes']}
        prompt = neuf['mission'][0][0]
        for passage in reversed(
            changes[self.IDS[0]]['set']['prompt']['replace']
        ):
            self.assertEqual(prompt.count(passage['new']), 1)
            prompt = prompt.replace(passage['new'], passage['old'])
        conn.execute(
            'UPDATE invocations SET prompt=?, role=? WHERE id=?',
            (
                prompt,
                changes[self.IDS[1]]['set']['role']['from'],
                'envoyer_par_le_web',
            ),
        )
        reponse = changes[self.IDS[2]]['set']
        conn.execute(
            'UPDATE invocation_output_fields SET choices=?, description=?'
            " WHERE invocation_id='envoyer_par_le_web' AND path='envoye'",
            (reponse['choices']['from'], reponse['description']['from']),
        )
        conn.execute(
            'UPDATE triggers SET confirm_text=? WHERE id=?',
            (
                changes[self.IDS[3]]['set']['confirm_text']['from'],
                'bouton_message_d_essai_reseau',
            ),
        )
        # La boucle de l'essai n'existe pas encore sur le serveur.
        conn.execute('DELETE FROM links WHERE id IN (?, ?)', self.LIENS)
        conn.execute(
            'DELETE FROM link_params WHERE link_id IN (?, ?)', self.LIENS
        )
        for table in (
            'invocation_settings',
            'invocation_tool_params',
            'invocation_tools',
        ):
            conn.execute(
                f'DELETE FROM {table} WHERE invocation_id=?', (self.COMPTEUR,)
            )
        conn.execute('DELETE FROM invocations WHERE id=?', (self.COMPTEUR,))
        conn.executemany(
            'DELETE FROM pipeline_changes WHERE id=?',
            [(i,) for i in self.IDS],
        )
        return conn, data, neuf

    def _resultats(self, conn: sqlite3.Connection) -> list[str]:
        return [
            str(
                conn.execute(
                    'SELECT result FROM pipeline_changes WHERE id=?', (ident,)
                ).fetchone()[0]
            )
            for ident in self.IDS
        ]

    def test_il_recoit_la_demande_de_contact_et_l_attente(self) -> None:
        conn, data, neuf = self._serveur()
        avant = self._etat(conn)
        self.assertIn(
            "n'envoie pas la demande sans note", avant['mission'][0][0]
        )
        self.assertEqual(avant['reponse'][0][0], 'oui, deja, non')
        self.assertEqual((avant['liens'], avant['compteur']), ([], []))
        seed_pipeline(conn, data)
        # Tout est, au caractère près, comme sur une instance neuve.
        apres = self._etat(conn)
        self.assertEqual(apres, neuf)
        consigne = apres['mission'][0][0]
        self.assertIn('« Se connecter » sans note (LinkedIn)', consigne)
        self.assertIn('rends envoye « attente »', consigne)
        self.assertIn("tu ne suis personne d'autre", consigne)
        self.assertNotIn("n'envoie pas la demande sans note", consigne)
        self.assertEqual(apres['reponse'][0][0], 'oui, deja, attente, non')
        self.assertEqual(
            [lien[:6] for lien in apres['liens']],
            [
                (
                    'essai_attend_un_contact',
                    'envoyer_par_le_web',
                    self.COMPTEUR,
                    'envoye',
                    '=',
                    'attente',
                ),
                (
                    'essai_retourne_voir',
                    self.COMPTEUR,
                    'envoyer_par_le_web',
                    'suite',
                    '=',
                    'encore',
                ),
            ],
        )
        # Le délai du rappel et le nombre d'essais viennent de la même
        # liste d'attentes de la Policy.
        liste = 'web_accounts.contact_waits_minutes'
        self.assertEqual(apres['liens'][1][6:], (f'{liste}[{{rappel}}]',) * 2)
        self.assertEqual(
            apres['tours'],
            [('round', 'task', 'rappel'), ('waits', 'fixed', liste)],
        )
        resultats = self._resultats(conn)
        self.assertEqual(resultats[0], 'prompt : 2 passage(s) remplacé(s)')
        for resultat in resultats[1:]:
            self.assertNotIn('gardé', resultat)
            self.assertNotIn('déjà à jour', resultat)
        # Une seconde fois ne change rien.
        seed_pipeline(conn, data)
        self.assertEqual(self._etat(conn), neuf)

    def test_une_instance_neuve_n_est_pas_touchee(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        self.assertEqual(
            self._resultats(conn),
            [
                'prompt déjà à jour',
                'role déjà à jour',
                'choices déjà à jour ; description déjà à jour',
                'confirm_text déjà à jour',
            ],
        )

    def _copie(
        self, conn: sqlite3.Connection, table: str, de: str, **change: str
    ) -> None:
        """Une ligne de plus dans ``table`` : celle dont l'``id`` est
        ``de``, avec ces colonnes changées."""
        cursor = conn.execute(f'SELECT * FROM {table} WHERE id=?', (de,))
        ligne = dict(
            zip(
                [d[0] for d in cursor.description],
                cursor.fetchone(),
                strict=True,
            )
        )
        ligne.update(change)
        conn.execute(
            f'INSERT INTO {table}({", ".join(ligne)})'
            f' VALUES({", ".join("?" * len(ligne))})',
            list(ligne.values()),
        )

    def test_le_serveur_du_21_novembre_recoit_la_liste_d_attentes(
        self,
    ) -> None:
        """Le 21 novembre au soir, le serveur a un compteur réglé à 6
        essais, deux liens à 10 minutes et trois réglages de délai. Le
        lendemain, tout suit une seule liste d'attentes : les anciens
        objets sont retirés, une boucle d'essai en cours s'arrête là."""
        from serge.interpreter.tasks import enqueue_task
        from serge.policy_store import ensure_policy, policy_en_vigueur

        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        neuf = self._etat(conn)
        self._copie(conn, 'invocations', self.COMPTEUR, id=self.VIEUX_COMPTEUR)
        conn.execute(
            'INSERT INTO invocation_settings(invocation_id, name, value)'
            " VALUES(?, 'essais_max', '6')",
            (self.VIEUX_COMPTEUR,),
        )
        for vieux, modele in zip(self.VIEUX_LIENS, self.LIENS, strict=True):
            self._copie(conn, 'links', modele, id=vieux)
        anciens = (
            'web_accounts.contact_retry_hours',
            'web_accounts.contact_wait_days',
            'web_accounts.trial_contact_retry_minutes',
        )
        for ident in anciens:
            self._copie(
                conn, 'policy_settings', 'web_accounts.inbox_days', id=ident
            )
        en_cours = enqueue_task(
            conn, self.VIEUX_COMPTEUR, {'rappel': '2'}, key='vieux-rappel'
        )
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        seed_pipeline(conn, data)
        ensure_policy(conn)
        # La boucle neuve est intacte ; l'ancienne est retirée.
        self.assertEqual(self._etat(conn), neuf)
        self.assertTrue(
            conn.execute(
                'SELECT deleted_at FROM invocations WHERE id=?',
                (self.VIEUX_COMPTEUR,),
            ).fetchone()[0]
        )
        self.assertEqual(
            [
                bool(r[0])
                for r in conn.execute(
                    'SELECT deleted_at FROM links WHERE id IN (?, ?)',
                    self.VIEUX_LIENS,
                )
            ],
            [True, True],
        )
        self.assertIsNone(
            conn.execute(
                'SELECT 1 FROM invocation_settings WHERE invocation_id=?',
                (self.VIEUX_COMPTEUR,),
            ).fetchone()
        )
        self.assertEqual(
            conn.execute(
                'SELECT status, last_error FROM tasks WHERE id=?', (en_cours,)
            ).fetchone(),
            ('cancelled', 'invocation retirée du pipeline'),
        )
        reglages = policy_en_vigueur(conn)['web_accounts']
        self.assertEqual(
            reglages['contact_waits_minutes'], [5, 60, 180, 360, 1440, 10080]
        )
        for ident in anciens:
            self.assertNotIn(ident.split('.')[1], reglages)

    def test_une_consigne_changee_dans_mission_control_est_gardee(
        self,
    ) -> None:
        conn, data, _ = self._serveur()
        a_la_main = str(self._etat(conn)['mission'][0][0]).replace(
            '3. Envoie le texte :', '3. Envoie le texte, sans te presser :'
        )
        conn.execute(
            "UPDATE invocations SET prompt=? WHERE id='envoyer_par_le_web'",
            (a_la_main,),
        )
        seed_pipeline(conn, data)
        apres = str(self._etat(conn)['mission'][0][0])
        # Le passage réécrit à la main est gardé ; l'autre, resté intact,
        # reçoit sa modification.
        self.assertIn('3. Envoie le texte, sans te presser :', apres)
        self.assertIn("tu ne suis personne d'autre", apres)
        self.assertIn('gardé', self._resultats(conn)[0])


class MotDePasseDuSiteTests(unittest.TestCase):
    """Le serveur du 22 novembre 2026 : « Créer un compte web » ne peut pas
    demander un mot de passe à la mesure du site (décision Q112)."""

    IDS = (
        'lot13_compte_outil_mot_de_passe',
        'lot13_compte_mot_de_passe_refuse',
    )
    OUTIL = 'changer_mot_de_passe_du_compte'

    def _outil(self, conn: sqlite3.Connection) -> list[tuple]:
        return [
            tuple(r)
            for r in conn.execute(
                'SELECT it.mode, it.max_calls, p.param_name, p.source, p.value'
                ' FROM invocation_tools it LEFT JOIN invocation_tool_params p'
                ' ON p.invocation_tool_id=it.id'
                " WHERE it.invocation_id='creer_compte_web' AND it.tool_id=?",
                (self.OUTIL,),
            )
        ]

    def _prompt(self, conn: sqlite3.Connection) -> str:
        return str(
            conn.execute(
                "SELECT prompt FROM invocations WHERE id='creer_compte_web'"
            ).fetchone()[0]
        )

    def test_il_recoit_l_outil_et_la_consigne(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        changes = {c['id']: c for c in data['changes']}
        neuf, outil = self._prompt(conn), self._outil(conn)
        self.assertEqual(
            outil, [('callable', '3', 'account', 'task', 'compte')]
        )
        # Une instance neuve a déjà tout.
        self.assertEqual(
            [
                conn.execute(
                    'SELECT result FROM pipeline_changes WHERE id=?', (i,)
                ).fetchone()[0]
                for i in self.IDS
            ],
            [f'{self.OUTIL} déjà là', 'prompt déjà à jour'],
        )
        # Le serveur d'avant : ni l'outil, ni le passage de la consigne.
        passage = changes[self.IDS[1]]['set']['prompt']['replace'][0]
        self.assertEqual(neuf.count(passage['new']), 1)
        conn.execute(
            "UPDATE invocations SET prompt=? WHERE id='creer_compte_web'",
            (neuf.replace(passage['new'], passage['old']),),
        )
        liens = [
            r[0]
            for r in conn.execute(
                'SELECT id FROM invocation_tools WHERE tool_id=?',
                (self.OUTIL,),
            )
        ]
        for lien in liens:
            conn.execute(
                'DELETE FROM invocation_tool_params WHERE'
                ' invocation_tool_id=?',
                (lien,),
            )
            conn.execute('DELETE FROM invocation_tools WHERE id=?', (lien,))
        conn.executemany(
            'DELETE FROM pipeline_changes WHERE id=?',
            [(i,) for i in self.IDS],
        )
        self.assertEqual(self._outil(conn), [])
        self.assertNotIn('Changer le mot de passe', self._prompt(conn))
        seed_pipeline(conn, data)
        self.assertEqual(self._prompt(conn), neuf)
        self.assertEqual(self._outil(conn), outil)
        # Une seconde fois ne change rien.
        seed_pipeline(conn, data)
        self.assertEqual(self._outil(conn), outil)


class ConnexionAvecGoogleTests(unittest.TestCase):
    """Le serveur du 26 novembre 2026 : quatre invocations se reconnectent
    à un compte par son mot de passe seulement (décision Q113)."""

    IDS = {
        'lot13_fouille_connexion_google': 'fouiller_reseau',
        'lot13_envoi_web_connexion_google': 'envoyer_par_le_web',
        'lot13_lecture_web_connexion_google': 'lire_messagerie',
        'lot13_verifier_connexion_google': 'verifier_compte_web',
    }

    def _prompts(self, conn: sqlite3.Connection) -> dict[str, str]:
        return {
            str(ident): str(prompt)
            for ident, prompt in conn.execute(
                'SELECT id, prompt FROM invocations WHERE id IN (?, ?, ?, ?)',
                tuple(self.IDS.values()),
            )
        }

    def test_elles_recoivent_la_reconnexion_par_google(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        changes = {c['id']: c for c in data['changes']}
        neufs = self._prompts(conn)
        for ident, invocation in self.IDS.items():
            # Une instance neuve a déjà la consigne.
            self.assertEqual(
                conn.execute(
                    'SELECT result FROM pipeline_changes WHERE id=?', (ident,)
                ).fetchone()[0],
                'prompt déjà à jour',
            )
            passage = changes[ident]['set']['prompt']['replace'][0]
            self.assertEqual(neufs[invocation].count(passage['new']), 1)
            conn.execute(
                'UPDATE invocations SET prompt=? WHERE id=?',
                (
                    neufs[invocation].replace(passage['new'], passage['old']),
                    invocation,
                ),
            )
        conn.executemany(
            'DELETE FROM pipeline_changes WHERE id=?', [(i,) for i in self.IDS]
        )
        for prompt in self._prompts(conn).values():
            self.assertNotIn('Continuer avec', prompt)
        seed_pipeline(conn, data)
        self.assertEqual(self._prompts(conn), neufs)
        for prompt in neufs.values():
            self.assertIn('se connecte avec Google', prompt)
            self.assertIn('« Appeler un humain »', prompt)


class PremierLancementB2BTests(unittest.TestCase):
    """Le serveur du 27 novembre 2026, avant le premier lancement en B2B
    (décision Q114) : il reçoit le texte de ce que Serge vend, la
    vérification d'une idée sur X, la réponse sans rendez-vous, et Apollo
    pour trouver des prospects."""

    CONSIGNES = {
        'b2b_formuler_a_consigne_x': 'formuler_a',
        'b2b_formuler_b_consigne_x': 'formuler_b',
        'b2b_choisir_business_consigne_x': 'choisir_business',
        'b2b_reponse_sans_rendez_vous': 'traiter_reponse',
        'b2b_prospects_consigne_apollo': 'trouver_prospects',
    }
    OUTILS = {
        'b2b_formuler_a_fouille_x': ('formuler_a', 'fouiller_x'),
        'b2b_formuler_b_fouille_x': ('formuler_b', 'fouiller_x'),
        'b2b_choisir_business_fouille_x': ('choisir_business', 'fouiller_x'),
        'b2b_prospects_outil_apollo': (
            'trouver_prospects',
            'chercher_sur_apollo',
        ),
    }
    TEXTE = 'b2b_ce_que_serge_vend'

    def _etat(self, conn: sqlite3.Connection) -> dict[str, list]:
        invocations = sorted(set(self.CONSIGNES.values()))
        return {
            'consignes': [
                tuple(r)
                for r in conn.execute(
                    'SELECT id, prompt FROM invocations WHERE id IN'
                    f' ({",".join("?" * len(invocations))}) ORDER BY id',
                    invocations,
                )
            ],
            'outils': [
                tuple(r)
                for r in conn.execute(
                    'SELECT it.invocation_id, it.tool_id, it.mode,'
                    ' it.max_calls, p.param_name, p.source, p.value'
                    ' FROM invocation_tools it JOIN invocation_tool_params p'
                    ' ON p.invocation_tool_id=it.id WHERE it.tool_id IN'
                    " ('fouiller_x', 'chercher_sur_apollo')"
                    ' ORDER BY it.invocation_id, it.tool_id, p.param_name'
                )
            ],
            'texte': [
                tuple(r)
                for r in conn.execute(
                    "SELECT body FROM serge_texts WHERE id='presentation'"
                )
            ],
        }

    def test_il_recoit_tout_le_lancement(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        changes = {c['id']: c for c in data['changes']}
        neuf = self._etat(conn)
        prompts = dict(neuf['consignes'])
        # Le serveur d'avant : sans les passages, sans les outils.
        for ident, invocation in self.CONSIGNES.items():
            passage = changes[ident]['set']['prompt']['replace'][0]
            self.assertEqual(prompts[invocation].count(passage['new']), 1)
            conn.execute(
                'UPDATE invocations SET prompt=? WHERE id=?',
                (
                    prompts[invocation].replace(
                        passage['new'], passage['old']
                    ),
                    invocation,
                ),
            )
        passage = changes[self.TEXTE]['set']['body']['replace'][0]
        conn.execute(
            "UPDATE serge_texts SET body=? WHERE id='presentation'",
            (neuf['texte'][0][0].replace(passage['new'], passage['old']),),
        )
        for invocation, outil in self.OUTILS.values():
            for (lien,) in conn.execute(
                'SELECT id FROM invocation_tools WHERE invocation_id=?'
                ' AND tool_id=?',
                (invocation, outil),
            ).fetchall():
                conn.execute(
                    'DELETE FROM invocation_tool_params WHERE'
                    ' invocation_tool_id=?',
                    (lien,),
                )
                conn.execute(
                    'DELETE FROM invocation_tools WHERE id=?', (lien,)
                )
        conn.executemany(
            'DELETE FROM pipeline_changes WHERE id=?',
            [(i,) for i in (*self.CONSIGNES, *self.OUTILS, self.TEXTE)],
        )
        avant = self._etat(conn)
        self.assertNotIn('produits web', avant['texte'][0][0])
        self.assertIn(
            'Un rendez-vous : confirme-le',
            dict(avant['consignes'])['traiter_reponse'],
        )
        # « Trouver des prospects » avait déjà « Fouiller X », pas Apollo.
        self.assertEqual(
            {(o[0], o[1]) for o in avant['outils']},
            {
                ('explorer_web', 'fouiller_x'),
                ('trouver_prospects', 'fouiller_x'),
            },
        )
        seed_pipeline(conn, data)
        apres = self._etat(conn)
        self.assertEqual(apres, neuf)
        texte = apres['texte'][0][0]
        self.assertIn('des produits web, et seulement cela', texte)
        self.assertIn('Serge ne téléphone pas', texte)
        reponse = dict(apres['consignes'])['traiter_reponse']
        self.assertNotIn('confirme-le', reponse)
        self.assertIn('ne promets\n  rien de tel', reponse)
        self.assertIn('voyez avec ma\n  collègue', reponse)
        self.assertIn(
            (
                'formuler_b',
                'fouiller_x',
                'callable',
                '2',
                'account',
                'fixed',
                'x',
            ),
            apres['outils'],
        )
        self.assertIn(
            (
                'trouver_prospects',
                'chercher_sur_apollo',
                'callable',
                'fouilles_max',
                'account',
                'fixed',
                'apollo',
            ),
            apres['outils'],
        )
        # Une seconde fois ne change rien.
        seed_pipeline(conn, data)
        self.assertEqual(self._etat(conn), neuf)

    def test_sans_compte_apollo_la_mission_le_dit(self) -> None:
        """Le compte Apollo n'existe pas encore : l'outil répond de faire
        sans, et « Trouver des prospects » cherche sur le web."""
        from serge.missions import mission

        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        rendu = mission(
            conn,
            'chercher_sur_apollo',
            {
                'invocation': 'fouiller_reseau',
                'account': 'apollo',
                'mission': 'des gérants de PME du bâtiment à Lyon',
                'task_id': 't_1',
            },
            'trouver_prospects',
        )
        self.assertFalse(rendu['ok'])
        self.assertIn('pas de compte « apollo » en service', rendu['detail'])
