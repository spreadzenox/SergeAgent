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

Ajouter un canal, c'est écrire son adaptateur et l'ajouter à ``ADAPTERS``,
avec ses réglages dans ``config/policy.yaml`` : le pipeline ne change pas.
Conception : ``docs/LOT8_CONCEPTION.md``, partie 1.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


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


# Les canaux branchés dans le code. Le lot 8 ajoute l'e-mail (PR 2) et
# l'appel (PR 3).
ADAPTERS: dict[str, Adapter] = {}


class ChannelError(ValueError):
    """Un canal n'est pas branché, ou un envoi a échoué."""


def adapter(channel: str) -> Adapter:
    """L'adaptateur d'un canal branché.

    Raises:
        ChannelError: Canal absent du code.
    """
    found = ADAPTERS.get(channel)
    if found is None:
        raise ChannelError(f'canal non branché : {channel}')
    return found
