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

Ajouter un canal, c'est écrire son adaptateur et l'ajouter à ``ADAPTERS``
(``serge/channels/adapters.py``), avec ses réglages dans
``config/policy.yaml`` : le pipeline ne change pas. Conception :
``docs/LOT8_CONCEPTION.md``, partie 1.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


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
    poll: Callable[[str], list[Incoming]] | None = None
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
