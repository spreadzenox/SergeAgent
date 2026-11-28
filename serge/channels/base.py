#!/usr/bin/env python3
"""Ce qu'est un canal pour le pipeline : un adaptateur, toujours le même.

Un adaptateur transporte un message, sans rien savoir d'une invocation ni
d'un business. Il a trois fonctions :

- ``send`` envoie un message et rend sa référence (pour l'e-mail, son
  Message-ID). L'adaptateur la tire du numéro de l'envoi : une réponse qui
  la cite est rattachée à son contact ;
- ``confirm`` dit si un envoi est parti (sa référence, ou ``''``) : c'est
  ce qui évite d'envoyer deux fois après un arrêt du programme ;
- ``poll``, pour un canal qui se relève (l'e-mail), rend les messages reçus
  depuis une date. Un canal qui reçoit en direct (le téléphone) n'en a pas.

Un canal peut avoir plusieurs boîtes (l'e-mail, décision Q120) : leur
liste est en base (page Policy, ``channels.<canal>.mailboxes``). ``poll``
reçoit cette liste et relève chaque boîte ; un message reçu dit la boîte
qui l'a reçu (``mailbox``), un envoi celle d'où il part (``sender``). Vide :
la boîte du serveur.

Ajouter un canal, c'est écrire son adaptateur et l'ajouter à ``ADAPTERS``
(``serge/channels/adapters.py``), avec ses réglages dans
``config/policy.yaml`` : le pipeline ne change pas. Conception :
``docs/LOT8_CONCEPTION.md``, partie 1.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.utils import getaddresses


def _always() -> bool:
    return True


@dataclass(frozen=True)
class Outgoing:
    """Un message à envoyer (une ligne de ``touches``)."""

    touch_id: str
    channel: str
    address: str
    subject: str
    body: str
    # La référence du message reçu auquel il répond, ou ''.
    in_reply_to: str = ''
    kind: str = ''
    # La boîte d'où il part (``touches.sender``) ; '' : celle du serveur.
    sender: str = ''


@dataclass(frozen=True)
class Incoming:
    """Un message reçu, tel que le rend la relève d'un canal."""

    external_ref: str
    address: str
    subject: str
    body: str
    # Sa propre référence (pour lui répondre dans le même fil).
    message_ref: str = ''
    # Les références des messages auxquels il répond (pour le rattacher).
    refs: tuple[str, ...] = ()
    native_type: str = ''
    # Les adresses à qui il est écrit (un e-mail), en minuscules.
    to: tuple[str, ...] = ()
    # La boîte de Serge qui l'a reçu ; '' : celle du serveur.
    mailbox: str = ''


@dataclass(frozen=True)
class Adapter:
    """Un canal branché : ses trois fonctions et sa description."""

    id: str
    title: str
    doc: str
    # La sorte d'adresse dans ``contact_addresses`` (email, phone…).
    address_channel: str
    code_path: str
    send: Callable[[Outgoing], str]
    confirm: Callable[[Outgoing], str]
    # ``poll(depuis, boîtes)`` : les boîtes à relever, lues en base.
    poll: Callable[[str, tuple[str, ...]], list[Incoming]] | None = None
    # Le canal est configuré sur ce serveur (pour l'e-mail : une boîte
    # Gmail ou SMTP/IMAP dans le fichier d'instance).
    ready: Callable[[], bool] = _always


class ChannelError(ValueError):
    """Un canal n'est pas branché, ou le canal a refusé le message."""


class ChannelLater(ChannelError):
    """Le canal ne peut pas maintenant : l'envoi attend ``until`` (ISO).

    Exemple : un appel hors des heures légales attend le prochain créneau
    (décision Q83).
    """

    def __init__(self, reason: str, until: str) -> None:
        super().__init__(reason)
        self.until = until


def recipients(headers: Mapping[str, str]) -> tuple[str, ...]:
    """Les adresses à qui un e-mail est écrit, en minuscules, d'après ses
    en-têtes (noms en minuscules) : ``To``, ``Cc`` et ``Delivered-To``.
    Exemple : « Serge <Serge+Calcu@exemple.fr> » → ``serge+calcu@exemple.fr``.
    """
    found = getaddresses(
        [headers.get(name, '') for name in ('to', 'cc', 'delivered-to')]
    )
    return tuple(dict.fromkeys(a.lower() for _n, a in found if '@' in a))
