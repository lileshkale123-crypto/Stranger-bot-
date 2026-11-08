"""In-memory matching state.

All methods are synchronous and contain no awaits, so under asyncio each call is
atomic. To move to Redis later, keep these method names and re-implement them.
"""
import time
from collections import deque


class Store:
    def __init__(self) -> None:
        # uid -> {"gender": str, "want": str | None, "since": float}  (insertion order = wait order)
        self.queue: dict[int, dict] = {}
        self.pairs: dict[int, int] = {}
        self._hits: dict[int, deque] = {}

    # ----- queue -----
    def enqueue(self, uid: int, gender: str, want: str | None) -> int | None:
        """Try to match immediately. Returns the partner id if matched,
        otherwise puts the user in the queue and returns None."""
        self.queue.pop(uid, None)
        for cid, c in self.queue.items():
            if (want is None or c["gender"] == want) and (c["want"] is None or c["want"] == gender):
                del self.queue[cid]
                self.pairs[uid] = cid
                self.pairs[cid] = uid
                return cid
        self.queue[uid] = {"gender": gender, "want": want, "since": time.monotonic()}
        return None

    def dequeue(self, uid: int) -> bool:
        return self.queue.pop(uid, None) is not None

    def in_queue(self, uid: int) -> bool:
        return uid in self.queue

    # ----- chats -----
    def partner_of(self, uid: int) -> int | None:
        return self.pairs.get(uid)

    def end_chat(self, uid: int) -> int | None:
        partner = self.pairs.pop(uid, None)
        if partner is not None:
            self.pairs.pop(partner, None)
        return partner

    # ----- stats -----
    def active_chats(self) -> int:
        return len(self.pairs) // 2

    def online(self) -> int:
        return len(self.pairs) + len(self.queue)

    # ----- rate limit -----
    def allow_message(self, uid: int, limit: int, window: float) -> bool:
        now = time.monotonic()
        hits = self._hits.setdefault(uid, deque())
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


store = Store()
