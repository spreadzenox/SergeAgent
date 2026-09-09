#!/usr/bin/env python3
"""Workers DET+LLM : consomment les work_items (classify, reply, judge...)."""

from __future__ import annotations

from serge.workers.call import run_voice_send
from serge.workers.classify import run_classify
from serge.workers.dispatch import execute
from serge.workers.listen import run_cluster, run_collect
from serge.workers.memory import run_apply, run_consolidate_worker
from serge.workers.poll import run_email_poll
from serge.workers.respond import run_judge_other, run_reply
from serge.workers.send import run_email_send
from serge.workers.voice import run_score

__all__ = [
    'execute',
    'run_apply',
    'run_classify',
    'run_cluster',
    'run_collect',
    'run_consolidate_worker',
    'run_email_poll',
    'run_email_send',
    'run_judge_other',
    'run_reply',
    'run_score',
    'run_voice_send',
]
