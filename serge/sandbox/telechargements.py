#!/usr/bin/env python3
"""Les fichiers qu'une page fait télécharger : les garder, les lire.

Un clic peut lancer un téléchargement (« Exporter en CSV », une facture en
PDF). Le fichier n'est pas dans la page : sans ce module, le modèle ne
saurait ni qu'il existe ni ce qu'il contient.

Le navigateur écrit le fichier dans son conteneur, dans ``DOSSIER``, sous
un nom de son choix. Serge l'en sort, le range avec le livrable
(``files/<business>/<livrable>/telechargements/``), lui fait une fiche dans
``artifacts``, et rend au modèle son nom, sa taille et son début. La suite
se lit avec l'action ``lire_telechargement``. Un fichier qui n'est pas du
texte (un PDF, une image) est gardé, sans être lu.

Exemple de ce que reçoit le modèle après un clic sur « Exporter en CSV » :
``{nom: 'export.csv', taille: '1,2 ko', lignes: 14, debut: 'date;calcul…'}``.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from serge.db.store import utcnow
from serge.paths import files_root
from serge.sandbox.chantier import chantier_id
from serge.sandbox.docker import DockerError, docker

# Où le navigateur écrit ce qu'il télécharge, dans son conteneur : un
# dossier qui existe partout et où il a le droit d'écrire.
DOSSIER = '/tmp'
# Ce qu'une lecture rend au plus : des lignes, et des caractères par ligne.
LIGNES = 40
LARGEUR = 400


def sortir(conteneur: str, chemin: str, destination: Path) -> None:
    """Sort un fichier téléchargé du conteneur du navigateur.

    Un navigateur qui tourne sur la machine même (les tests) a écrit le
    fichier ici : il est déplacé.

    Raises:
        DockerError: Le fichier n'a pas pu être sorti du conteneur.
    """
    source = Path(chemin)
    if source.is_file():
        shutil.move(str(source), destination)
        return
    docker(['cp', f'{conteneur}:{chemin}', str(destination)], timeout=120)
    docker(['exec', conteneur, 'rm', '-f', chemin], timeout=30, check=False)


def _taille(octets: int) -> str:
    if octets < 1000:
        return f'{octets} octets'
    if octets < 1_000_000:
        return f'{octets / 1000:.1f} ko'.replace('.', ',')
    return f'{octets / 1_000_000:.1f} Mo'.replace('.', ',')


def _texte(chemin: Path) -> list[str] | None:
    """Les lignes d'un fichier texte, ou ``None`` s'il n'en est pas un."""
    contenu = chemin.read_bytes()
    if b'\x00' in contenu[:4000]:
        return None
    try:
        texte = contenu.decode('utf-8-sig')
    except UnicodeDecodeError:
        texte = contenu.decode('latin-1')
    return texte.splitlines()


@dataclass
class Telechargements:
    """Les téléchargements d'une session du navigateur."""

    # Ceux que le navigateur a commencés et que Serge n'a pas encore sortis.
    attente: list[Any] = field(default_factory=list)
    # Ceux qui sont gardés : le nom donné au modèle, et le fichier.
    fichiers: dict[str, Path] = field(default_factory=dict)

    def recevoir(self, download: Any) -> None:
        """Note un téléchargement qui commence (appelée par Playwright)."""
        self.attente.append(download)

    def _nom(self, propose: str) -> str:
        """Un nom de fichier sûr, et pas encore pris dans la session."""
        nom = re.sub(r'[^\w.\- ]', '_', Path(propose or 'fichier').name)
        nom = nom.strip(' .') or 'fichier'
        base, rang = nom, 2
        while nom in self.fichiers:
            tige, point, suffixe = base.rpartition('.')
            nom = f'{tige}-{rang}.{suffixe}' if point else f'{base}-{rang}'
            rang += 1
        return nom

    def ramasser(
        self,
        conn: sqlite3.Connection,
        args: dict[str, Any],
        conteneur: str,
    ) -> list[dict[str, Any]]:
        """Sort et range les téléchargements commencés ; rend, pour chacun,
        ce que le modèle doit en savoir."""
        faits = []
        attente, self.attente = self.attente, []
        for download in attente:
            propose = str(download.suggested_filename or '')
            try:
                echec = download.failure()
                if echec:
                    faits.append({'nom': propose, 'echec': str(echec)[:200]})
                    continue
                nom = self._nom(propose)
                chemin = self._dossier(args) / nom
                sortir(conteneur, str(download.path()), chemin)
            except (DockerError, OSError, RuntimeError) as exc:
                faits.append({'nom': propose, 'echec': str(exc)[:200]})
                continue
            except Exception as exc:  # noqa: BLE001 — Playwright, un onglet fermé
                faits.append({'nom': propose, 'echec': str(exc)[:200]})
                continue
            self.fichiers[nom] = chemin
            self._ficher(conn, args, chemin)
            faits.append(self.lire(nom))
        return faits

    def _dossier(self, args: dict[str, Any]) -> Path:
        venture_id = str(args.get('venture_id') or '')
        dossier = files_root() / chantier_id(venture_id, 'x').removesuffix(
            '-x'
        )
        dossier = (
            dossier / str(args.get('deliverable') or '') / 'telechargements'
        )
        dossier = dossier / (str(args.get('task_id') or '') or 'sans-tache')
        dossier.mkdir(parents=True, exist_ok=True)
        return dossier

    def _ficher(
        self, conn: sqlite3.Connection, args: dict[str, Any], chemin: Path
    ) -> None:
        contenu = chemin.read_bytes()
        ident = f'art_{hashlib.sha256(str(chemin).encode()).hexdigest()[:12]}'
        conn.execute(
            'INSERT OR REPLACE INTO artifacts(id, venture_id, kind, version,'
            ' path_or_url, hash, size_bytes, task_id, created_at)'
            " VALUES(?,?,'telechargement',1,?,?,?,?,?)",
            (
                ident,
                str(args.get('venture_id') or ''),
                str(chemin),
                hashlib.sha256(contenu).hexdigest(),
                len(contenu),
                str(args.get('task_id') or ''),
                utcnow(),
            ),
        )

    def lire(self, nom: str = '', ligne: int = 1) -> dict[str, Any]:
        """Un fichier gardé (le dernier, sans nom) : sa taille, et ses lignes
        à partir de ``ligne`` s'il est du texte."""
        nom = nom or (list(self.fichiers)[-1] if self.fichiers else '')
        chemin = self.fichiers.get(nom)
        if chemin is None:
            connus = ', '.join(self.fichiers) or 'aucun'
            return {
                'nom': nom,
                'echec': f'aucun fichier téléchargé de ce nom (connus : {connus})',
            }
        fait: dict[str, Any] = {
            'nom': nom,
            'taille': _taille(chemin.stat().st_size),
        }
        lignes = _texte(chemin)
        if lignes is None:
            fait['contenu'] = (
                'pas du texte : gardé avec le livrable, sans être lu'
            )
            return fait
        debut = max(1, ligne)
        fait['lignes'] = len(lignes)
        morceau = lignes[debut - 1 : debut - 1 + LIGNES]
        fait['debut' if debut == 1 else f'a_partir_de_la_ligne_{debut}'] = (
            '\n'.join(x[:LARGEUR] for x in morceau)
        )
        if debut - 1 + LIGNES < len(lignes):
            fait['suite'] = (
                f'lire_telechargement, text « {nom} », line {debut + LIGNES}'
            )
        return fait
