#!/usr/bin/env python3
"""Les canaux branchés dans le code : un adaptateur par canal.

Un canal est branché quand son adaptateur est ici **et** qu'il est
configuré sur ce serveur. Exemple : l'e-mail est dans le code, mais une
instance sans boîte Gmail ni SMTP/IMAP ne l'a pas branché. Le catalogue
``canaux`` le dit (``serge/canaux.py``). Le lot 8 ajoute l'appel (PR 3).
"""

from __future__ import annotations

from serge.channels import mail
from serge.channels.base import Adapter, ChannelError

ADAPTERS: dict[str, Adapter] = {mail.ADAPTER.id: mail.ADAPTER}


def adapter(channel: str) -> Adapter:
    """L'adaptateur d'un canal branché.

    Raises:
        ChannelError: Canal absent du code, ou pas configuré ici.
    """
    found = ADAPTERS.get(channel)
    if found is None or not found.ready():
        raise ChannelError(f'canal non branché : {channel}')
    return found
