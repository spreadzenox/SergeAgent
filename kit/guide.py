#!/usr/bin/env python3
"""Interactive installer guide (LLM). Declared P2 point, never fatal."""

from __future__ import annotations

from typing import Any

from kit.openrouter import OpenRouterError, chat_completion

# LLM-CHECKLIST: entree=oui (questions libres FR) | sortie=oui (explication
# courte, conseil procédural) | info_externe=non | derive=oui (formulations)
# LLM-RISK: propagation=faible (lecture seule, aucun état modifié ; le pire
# cas est un mauvais conseil affiché, l'installateur décide toujours)
# LLM-FALLBACK: static TOPIC_HINTS below, then generic message. Never raises.
# LLM-BUDGET: mesuré (1 call/question, ~500 tokens max) ; alerte hors scope
# (installer éphémère, pas de boucle).

SYSTEM_PROMPT = (
    'Tu es le guide d\u2019installation de Serge (opérateur économique '
    'autonome, kit instance). Tu aides en français, simplement, sans jargon '
    'interne (ou en le définissant). Réponses courtes (5-8 lignes max), '
    'concrètes, orientées action. Tu ne vois aucun secret et tu n\u2019en '
    'demandes jamais. Si tu ne sais pas, dis-le et propose l\u2019option '
    'la plus sûre.'
)

TOPIC_HINTS = {
    'modeles': (
        'T1 = rapide/économique (classifications, résumés), T2 = défaut '
        '(rédaction, dialogue), T3 = stratège (plans, diagnostics rares). '
        'Les recommandations sont celles du VPS Julien (testées en prod). '
        'Garde-les sauf raison précise.'
    ),
    'instance': (
        'instance_id = nom unique de CE déploiement (ex. mon-vps, pas '
        'julien-vps). mode : sandbox pour tester (argent et voix coupés), '
        'live quand tout est vérifié.'
    ),
    'features': (
        'Tout ou rien : tout on sauf metagrok. Chaque feature on exige ses '
        'secrets — mets off ce que tu ne peux pas provisionner maintenant, '
        'tu réactiveras plus tard.'
    ),
    'phone': (
        'Option A = SIM + Android pour les OTP (obligatoire si Serge crée '
        'des comptes). Option B = A + trunk SIP avec numéro NPV pour la '
        'voix commerciale. Jamais de prospection en 06/07 (illégal).'
    ),
    'discord': (
        'Crée un serveur Discord privé : 1 forum (tickets), 1 canal urgent, '
        '1 canal digest. Active le mode développeur, copie les IDs (clic '
        'droit → copier l’identifiant) du serveur, des 3 canaux et de ton '
        'compte owner. Le token bot est demandé à l’étape secrets.'
    ),
    'secrets': (
        'Les secrets ne vont QUE dans le sidecar chiffré (age), jamais dans '
        'le TOML. Chaque feature on exige sa clé — prépare-les avant de '
        'continuer.'
    ),
    'mandat': (
        'Le mandat dit ce que Serge a le droit de faire. En sandbox, argent '
        'et voix sortante sont coupés même si demandés.'
    ),
    'mailbox': (
        'Boîte email de confiance en SMTP/IMAP (Infomaniak par défaut) : '
        'envoi direct + lecture des réponses, sans OAuth ni navigateur. '
        'Le mot de passe (ou app password) est demandé à l’étape secrets.'
    ),
}


class Guide:
    """LLM install guide. Offline-safe: static hints when the API fails."""

    def __init__(
        self,
        api_key: str = '',
        model: str = '',
        referer: str = '',
        enabled: bool = True,
    ) -> None:
        """Build a guide.

        Args:
            api_key: OpenRouter key (in-memory, header only).
            model: Guide model id (defaults to the T2 choice).
            referer: Optional HTTP referer.
            enabled: False disables LLM calls (static hints only).
        """
        self.api_key = api_key
        self.model = model
        self.referer = referer
        self.enabled = enabled

    @property
    def ready(self) -> bool:
        """True when live LLM answers are possible."""
        return bool(self.enabled and self.api_key and self.model)

    def ask(self, question: str, topic: str = '') -> str:
        """Answer an installer question. Never raises, never leaks secrets.

        Args:
            question: Free-text question in French.
            topic: Current wizard step (modeles, features, phone...).

        Returns:
            French answer: live LLM when ready, else the static hint for
            the topic, else a generic fallback.
        """
        hint = TOPIC_HINTS.get(topic, '')
        if not self.ready:
            return hint or (
                'Guide hors-ligne (pas de clé ou désactivé). Continue avec '
                'les valeurs recommandées — elles sont sûres.'
            )
        context = f'Contexte (étape installateur) : {topic}. ' if topic else ''
        if hint:
            context += f'Repère validé : {hint} '
        try:
            return chat_completion(
                self.api_key,
                self.model,
                [
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {
                        'role': 'user',
                        'content': f'{context}Question : {question}',
                    },
                ],
                self.referer,
            )
        except (OpenRouterError, ValueError):
            if hint:
                return (
                    f'{hint} (guide en ligne indisponible — réponse locale).'
                )
            return (
                'Guide en ligne indisponible (réseau ou clé). Garde la valeur '
                'recommandée et continue — rien n\u2019est bloquant.'
            )

    def topic_hint(self, topic: str) -> str:
        """Static hint for a topic (offline-safe).

        Args:
            topic: Wizard step key.

        Returns:
            The static hint, or '' when unknown.
        """
        return TOPIC_HINTS.get(topic, '')


def summarize_answers_for_guide(answers: dict[str, Any]) -> str:
    """Compact non-secret summary for guide context.

    Args:
        answers: Wizard answers (may contain secrets — never included).

    Returns:
        One-line summary: instance_id, mode, features on, models.
    """
    features = answers.get('features') or {}
    active = sorted(name for name, on in features.items() if on)
    llm = answers.get('llm') or {}
    return (
        f'instance={answers.get("instance_id")} '
        f'mode={answers.get("mode")} '
        f'features={",".join(active)} '
        f'models={llm.get("t1_model")}/{llm.get("t2_model")}/'
        f'{llm.get("t3_model")}'
    )
