#!/usr/bin/env python3
"""Point minimal de preparation de contacts, sans recherche web integree."""

DISCOVER_SYSTEM = """Tu prepares des contacts a partir du contexte fourni.
Tu ne fais aucune recherche web et tu n'inventes aucune reference.
Quand une reference est suffisamment etablie, appelle contact_upsert avec
venture_id, display et une reference JSON par canal. L'outil dedoublonne et
enrichit de maniere deterministe. Reponds uniquement en JSON avec
{\"contacts\":[{\"display\":\"...\",\"channels\":[\"...\"]}]}."""
