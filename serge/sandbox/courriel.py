#!/usr/bin/env python3
"""Les e-mails des produits (lot 11) : la boîte d'essai, l'envoi en prod,
la boîte du relecteur.

- **La boîte d'essai** : un Mailpit dans son conteneur (``serge-boite``),
  sur le réseau des chantiers. Dans un chantier et en staging, le produit
  envoie ses e-mails par son SMTP (``serge-boite:1025``) : ils y restent,
  quelle que soit l'adresse, et rien ne part. Le relecteur les y lit, et
  Julien et Clem dans Mission Control (fiche du business).
- **En prod**, le produit envoie par le SMTP de Resend avec sa propre clé,
  qui ne sait qu'envoyer : Serge la crée la première fois avec la clé
  maîtresse (``secrets/resend.key``), par « Appeler une API », et la range
  dans ``secrets/resend-<business>.key``. Elle se révoque sans toucher aux
  autres produits. L'expéditeur : ``<nom court>@<domaine d'envoi>``,
  toujours un sous-domaine de Serge (page Policy, Q96).
- **La boîte du relecteur** : ``relecteur-<tâche>@<domaine de la boîte>``
  (page Policy), une adresse par essai, jamais celle de Serge. En staging,
  ses e-mails arrivent dans la boîte d'essai ; en prod, par la réception
  de Resend.

Le produit reçoit ``SMTP_HOST``, ``SMTP_PORT``, ``SMTP_USER``,
``SMTP_PASS`` et ``MAIL_FROM`` dans son environnement : le même code
marche partout.
"""

from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from serge.paths import config_root
from serge.policy_store import policy_en_vigueur
from serge.sandbox.docker import (
    NETWORK,
    DockerError,
    docker,
    ensure_network,
    journal,
)
from serge.secrets import read_secret_file

BOITE = 'serge-boite'
SMTP_ESSAI = '1025'
# Le SMTP de Resend : STARTTLS sur 587, l'utilisateur est toujours
# « resend », le mot de passe est la clé du produit.
SMTP_PROD = ('smtp.resend.com', '587', 'resend')
# Le domaine d'une adresse quand rien n'est réglé : il n'existe pas, un
# e-mail ne part jamais vers lui.
INVALIDE = 'essai.invalid'
LIENS = re.compile(r'https?://[^\s"\'<>)\]]+')
TEXTE_MAX = 4000


def _reglages(conn: sqlite3.Connection) -> dict[str, Any]:
    policy = policy_en_vigueur(conn)
    return {
        **(policy.get('courriel') or {}),
        'boite': (policy.get('sandbox') or {}).get('boite') or {},
    }


def ensure_boite(conn: sqlite3.Connection) -> None:
    """Lance la boîte d'essai si elle ne tourne pas.

    Elle n'écoute que sur le réseau des chantiers (SMTP) et sur la machine
    (son API, pour Serge) : jamais depuis Internet.

    Raises:
        DockerError: Docker a refusé.
    """
    boite = _reglages(conn)['boite']
    etat = docker(
        ['ps', '-a', '--filter', f'name=^{BOITE}$', '--format', '{{.State}}'],
        timeout=30,
    ).stdout.strip()
    if etat == 'running':
        return
    if etat:
        docker(['start', BOITE], timeout=120)
        return
    ensure_network()
    docker(
        [
            'run',
            '-d',
            '--name',
            BOITE,
            '--restart',
            'unless-stopped',
            '--network',
            NETWORK,
            '-p',
            f'127.0.0.1:{int(boite["port"])}:8025',
            '-e',
            'MP_SMTP_AUTH_ACCEPT_ANY=1',
            '-e',
            'MP_SMTP_AUTH_ALLOW_INSECURE=1',
            '-e',
            'MP_MAX_MESSAGES=2000',
            str(boite['image']),
        ],
        timeout=600,
    )


def expediteur(conn: sqlite3.Connection, nom_court: str) -> str:
    """L'adresse d'expédition d'un produit : ``calcudevis@envoi.<domaine>``."""
    domaine = str(_reglages(conn).get('domaine_envoi') or '').strip()
    return f'{nom_court or "produit"}@{domaine or INVALIDE}'


def env_essai(conn: sqlite3.Connection, nom_court: str) -> dict[str, str]:
    """L'environnement d'envoi d'un chantier ou d'un staging : la boîte
    d'essai, sans identifiant."""
    return {
        'SMTP_HOST': BOITE,
        'SMTP_PORT': SMTP_ESSAI,
        'SMTP_USER': '',
        'SMTP_PASS': '',
        'MAIL_FROM': expediteur(conn, nom_court),
    }


def env_prod(
    conn: sqlite3.Connection,
    venture_id: str,
    nom_court: str,
    invocation_id: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """L'environnement d'envoi de la prod, et son secret (la clé du
    produit, créée la première fois).

    Raises:
        DockerError: Pas de domaine d'envoi réglé, ou la clé n'a pas pu
            être créée ; la raison est notée au journal.
    """
    if not str(_reglages(conn).get('domaine_envoi') or '').strip():
        message = 'pas de domaine d’envoi des e-mails (page Policy, E-mails)'
        journal(message)
        raise DockerError(message)
    hote, port, utilisateur = SMTP_PROD
    env = {
        'SMTP_HOST': hote,
        'SMTP_PORT': port,
        'SMTP_USER': utilisateur,
        'MAIL_FROM': expediteur(conn, nom_court),
    }
    return env, {'SMTP_PASS': cle_produit(conn, venture_id, invocation_id)}


def cle_produit(
    conn: sqlite3.Connection, venture_id: str, invocation_id: str
) -> str:
    """La clé d'envoi d'un produit : lue si elle existe, sinon créée.

    Raises:
        DockerError: Resend a refusé (la raison est notée au journal).
    """
    from serge.connecteurs.appel import call_api

    fichier = config_root() / 'secrets' / f'resend-{venture_id}.key'
    cle = read_secret_file(fichier)
    if cle:
        return cle
    reponse = call_api(
        conn,
        'resend_creer_cle',
        {'name': f'produit-{venture_id}', 'permission': 'sending_access'},
        invocation_id,
    )
    brut = reponse.get('data')
    data: dict[str, Any] = brut if isinstance(brut, dict) else {}
    cle = str(data.get('token') or '')
    if not reponse.get('ok') or not cle:
        message = (
            f'clé d’envoi du produit pas créée : HTTP {reponse.get("status")}'
            f' {str(data.get("message") or data.get("erreur") or "")[:200]}'
        )
        journal(message)
        raise DockerError(message)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    descripteur = os.open(fichier, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descripteur, 'w', encoding='utf-8') as sortie:
        sortie.write(cle + '\n')
    journal(f'clé d’envoi créée pour {venture_id}')
    return cle


def adresse_relecteur(conn: sqlite3.Connection, task_id: str) -> str:
    """L'adresse du relecteur pour une tâche : une par essai."""
    domaine = str(_reglages(conn).get('boite_relecteur') or '').strip()
    suffixe = task_id.removeprefix('t_')[:12] or 'essai'
    return f'relecteur-{suffixe}@{domaine or INVALIDE}'


def _get(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=15) as reponse:
        return json.loads(reponse.read().decode('utf-8'))


def _lisible(texte: str, page: str) -> tuple[str, list[str]]:
    """Le texte d'un e-mail (celui de sa page HTML s'il n'en a pas) et ses
    liens, dans l'ordre, sans doublon."""
    liens = list(dict.fromkeys(LIENS.findall(f'{texte}\n{page}')))
    if not texte.strip() and page:
        texte = html.unescape(re.sub(r'<[^>]+>', ' ', page))
    return re.sub(r'[ \t]+', ' ', texte).strip()[:TEXTE_MAX], liens


def lire_essai(
    conn: sqlite3.Connection, requete: str, limite: int = 10
) -> list[dict[str, Any]]:
    """Les e-mails de la boîte d'essai qui répondent à une recherche
    Mailpit (``to:"<adresse>"``, ``from:<nom court>@``), les plus récents
    d'abord.

    Raises:
        OSError: La boîte d'essai ne répond pas.
    """
    port = int(_reglages(conn)['boite']['port'])
    base = f'http://127.0.0.1:{port}/api/v1'
    query = urllib.parse.urlencode({'query': requete, 'limit': limite})
    trouves = _get(f'{base}/search?{query}').get('messages') or []
    messages = []
    for item in trouves:
        detail = _get(f'{base}/message/{urllib.parse.quote(str(item["ID"]))}')
        texte, liens = _lisible(
            str(detail.get('Text') or ''), str(detail.get('HTML') or '')
        )
        messages.append(
            {
                'de': str((item.get('From') or {}).get('Address') or ''),
                'a': ', '.join(
                    str(d.get('Address') or '') for d in item.get('To') or []
                ),
                'objet': str(item.get('Subject') or ''),
                'date': str(item.get('Created') or ''),
                'texte': texte,
                'liens': liens,
            }
        )
    return messages


def _lire_resend(
    conn: sqlite3.Connection, adresse: str, invocation_id: str
) -> list[dict[str, Any]]:
    """Les e-mails reçus par Resend pour cette adresse (la prod)."""
    from serge.connecteurs.appel import call_api

    liste = call_api(conn, 'resend_recus', {'limit': 50}, invocation_id)
    brut = liste.get('data')
    data: dict[str, Any] = brut if isinstance(brut, dict) else {}
    messages = []
    for item in (data.get('data') or [])[:50]:
        if adresse.lower() not in [
            str(a).lower() for a in item.get('to') or []
        ]:
            continue
        detail = call_api(
            conn, 'resend_recu', {'id': str(item.get('id'))}, invocation_id
        ).get('data')
        detail = detail if isinstance(detail, dict) else {}
        texte, liens = _lisible(
            str(detail.get('text') or ''), str(detail.get('html') or '')
        )
        messages.append(
            {
                'de': str(item.get('from') or ''),
                'a': adresse,
                'objet': str(item.get('subject') or ''),
                'date': str(item.get('created_at') or ''),
                'texte': texte,
                'liens': liens,
            }
        )
        if len(messages) >= 5:
            break
    return messages


def boite_relecteur(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    invocation_id: str,
) -> dict[str, Any]:
    """Capacité « Ma boîte e-mail » : l'adresse du relecteur pour cette
    tâche, et les e-mails qu'elle a reçus.

    Elle attend qu'un e-mail arrive, au plus le temps réglé (page Policy) :
    exemple, un e-mail de validation envoyé juste après l'inscription.
    """
    reglages = _reglages(conn)
    adresse = adresse_relecteur(conn, str(args.get('task_id') or ''))
    attendre = args.get('wait') not in (False, 'false', '0', 'non')
    fin = time.monotonic() + (float(reglages['attente_s']) if attendre else 0)
    prod = adresse.endswith(f'@{reglages.get("boite_relecteur") or "-"}')
    erreurs: list[str] = []
    while True:
        messages: list[dict[str, Any]] = []
        try:
            messages += lire_essai(conn, f'to:"{adresse}"', 5)
        except (OSError, ValueError) as exc:
            erreurs = [f'boîte d’essai injoignable : {exc}']
        if prod:
            messages += _lire_resend(conn, adresse, invocation_id)
        if messages or time.monotonic() >= fin:
            break
        time.sleep(3)
    for erreur in erreurs:
        journal(erreur)
    resultat: dict[str, Any] = {
        'ok': True,
        'adresse': adresse,
        'messages': messages,
    }
    if not messages:
        resultat['detail'] = 'aucun e-mail reçu à cette adresse pour l’instant'
    if erreurs and not messages:
        resultat.update(ok=False, code='boite_injoignable', detail=erreurs[0])
    return resultat


def envoi_du_produit(
    conn: sqlite3.Connection,
    target: str,
    venture_id: str,
    nom_court: str,
    invocation_id: str,
) -> tuple[list[str], dict[str, str]]:
    """Ce qu'un produit publié reçoit pour envoyer ses e-mails : ses
    options ``docker run`` (variables et réseau), et ses secrets.

    En staging, la boîte d'essai (lancée au besoin) ; en prod, Resend.

    Raises:
        DockerError: Voir ``env_prod`` et ``ensure_boite``.
    """
    if target == 'prod':
        env, secrets = env_prod(conn, venture_id, nom_court, invocation_id)
        reseau: list[str] = []
    else:
        ensure_boite(conn)
        env, secrets = env_essai(conn, nom_court), {}
        reseau = ['--network', NETWORK]
    options = [flag for k, v in env.items() for flag in ('-e', f'{k}={v}')]
    return [*options, *reseau], secrets
