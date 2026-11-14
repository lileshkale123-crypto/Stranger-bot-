"""Keeps live chats alive across redeploys.

Every few seconds the in-memory state (human pairs, search queue, AI sessions) is saved to the
database. On boot it is restored before polling starts, so a GitHub push no longer ends chats.
`boot_id` makes sure only the newest deployment owns the snapshot: when a newer deployment takes
over, the old one notices within a few seconds and stops polling by itself.
"""
import json, logging, time, uuid

import ai_partner, chat, db
from store import store

log = logging.getLogger(__name__)
BOOT_ID = uuid.uuid4().hex
INTERVAL = 4.0          # seconds between saves
MAX_AGE = 600.0         # a snapshot older than this (bot was down 10+ min) is ignored


def _snapshot() -> dict:
    now = time.monotonic()
    return {
        "pairs": {str(k): v for k, v in store.pairs.items()},
        "queue": {str(k): {"gender": v["gender"], "want": v["want"], "age": now - v["since"]}
                  for k, v in store.queue.items()},
        "ai": [ai_partner.dump_session(s) for s in list(ai_partner._sessions.values())],
    }


async def save() -> bool:
    """False only when a newer deployment owns the snapshot."""
    try:
        return await db.save_state(BOOT_ID, json.dumps(_snapshot()))
    except Exception:
        log.exception("state save failed")
        return True


async def restore(bot) -> None:
    n_pairs = n_queue = n_ai = 0
    try:
        row = await db.load_state()
        if row and row[1] < MAX_AGE:
            data, downtime = json.loads(row[0]), row[1]
            now = time.monotonic()
            store.pairs.update({int(k): int(v) for k, v in data.get("pairs", {}).items()})
            for k, v in data.get("queue", {}).items():
                store.queue[int(k)] = {"gender": v["gender"], "want": v["want"], "since": now - v["age"] - downtime}
            ai_partner.restore_sessions(bot, data.get("ai", []), downtime)
            for uid in [u for u, p in store.pairs.items() if u > 0 and p < 0 and u not in ai_partner._sessions]:
                store.end_chat(uid)                       # AI chat whose session was lost
            chat.resume_queue(bot)
            n_pairs = sum(1 for u in store.pairs if u > 0)
            n_queue, n_ai = len(store.queue), len(ai_partner._sessions)
    except Exception:
        log.exception("state restore failed, starting clean")
        store.pairs.clear()
        store.queue.clear()
    await db.save_state(BOOT_ID, json.dumps(_snapshot()), takeover=True)
    log.info("Restored %s chats (%s with AI), %s searching", n_pairs, n_ai, n_queue)
