#!/usr/bin/env python3
"""Les boîtes de dialogue du navigateur : message, question, saisie.

Une page peut ouvrir une boîte du navigateur lui-même : un message
(``alert``), une question à laquelle on répond « OK » ou « Annuler »
(``confirm``), un texte à taper (``prompt``). Cette boîte n'est pas dans la
page : le modèle ne la voit ni dans la page lue ni sur une capture, et ne
peut pas y cliquer. Tant qu'elle est ouverte, la page ne fait plus rien.

Serge y répond donc tout de suite, à la place du modèle, et lui dit ce qui
s'est passé dans le résultat de son action. Sans réponse préparée, un
message est fermé par « OK », une question ou une saisie par « Annuler »
(rien n'est fait). Pour y répondre, le modèle prépare sa réponse avec
l'action ``accepter_dialogue`` (avec le texte à taper, pour une saisie) ou
``refuser_dialogue``, puis refait l'action qui ouvre la boîte. Une réponse
préparée sert une fois, à la boîte suivante.

Exemple : le bouton « Enregistrer » d'un produit demande un nom dans une
saisie. ``accepter_dialogue`` avec « Devis Dupont », puis ``cliquer`` sur
« Enregistrer » : le calcul est enregistré sous ce nom.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SORTES = {
    'alert': 'message',
    'confirm': 'question',
    'prompt': 'saisie',
    'beforeunload': 'quitter la page',
}
# Ce que le modèle doit faire d'une question ou d'une saisie refermée.
CONSEIL = (
    'Pour y répondre : action accepter_dialogue (avec le texte à taper,'
    ' pour une saisie) ou refuser_dialogue, puis refais l’action qui a'
    ' ouvert la boîte.'
)


@dataclass
class Dialogues:
    """Les boîtes de dialogue d'une session du navigateur."""

    # La réponse préparée pour la prochaine boîte : (accepter, texte).
    preparee: tuple[bool, str] | None = None
    # Ce qui est arrivé depuis le dernier résultat rendu au modèle.
    vus: list[str] = field(default_factory=list)

    def preparer(self, accepter: bool, texte: str = '') -> None:
        self.preparee = (accepter, texte)

    def repondre(self, dialog: Any) -> None:
        """Répond à une boîte qui s'ouvre (appelée par Playwright)."""
        sorte = str(dialog.type)
        preparee, self.preparee = self.preparee, None
        accepter, texte = preparee or (sorte not in ('confirm', 'prompt'), '')
        try:
            if not accepter:
                dialog.dismiss()
            elif sorte == 'prompt':
                dialog.accept(texte)
            else:
                dialog.accept()
        except Exception:  # noqa: BLE001 — une boîte déjà fermée
            return
        if not accepter:
            fait = 'refusée (Annuler)' if preparee else 'refermée sans réponse'
        elif sorte == 'prompt':
            fait = f'répondu « {texte} »'
        else:
            fait = 'acceptée (OK)' if sorte == 'confirm' else 'fermé (OK)'
        nom = SORTES.get(sorte, sorte)
        phrase = f'{nom} « {str(dialog.message)[:300]} » : {fait}'
        if preparee is None and not accepter:
            phrase += f'. {CONSEIL}'
        self.vus.append(phrase)
        del self.vus[:-10]

    def raconter(self) -> list[str]:
        """Ce qui est arrivé depuis le dernier appel, puis on oublie."""
        vus, self.vus = self.vus, []
        return vus
