import time
from collections import deque

class Store:
    def __init__(self) -> None:
        self.queue: dict[int, dict] = {}
        self.pairs: dict[int, int] = {}
        self._hits: dict[int, deque] = {}

    def enqueue(self, uid: int, gender: str, want: str | None) -> int | None:
        self.queue.pop(uid, None)
        for cid, c in self.queue.items():
            if (want is None or c["gender"] == want) and (c["want"] is None or c["want"] == gender):
                del self.queue[cid]
                self.pairs[uid] = cid
                self.pairs[cid] = uid
                return cid
        self.queue[uid] = {"gender": gender, "want": want, "since": time.monotonic()}
        return None

    def pair_ai(self, uid: int) -> int | None:
        if uid not in self.queue:
            return None
        del self.queue[uid]
        ai_id = -uid
        self.pairs[uid] = ai_id
        self.pairs[ai_id] = uid
        return ai_id

    @staticmethod
    def is_ai(partner_id: int | None) -> bool:
        return partner_id is not None and partner_id < 0

    def dequeue(self, uid: int) -> bool:
        return self.queue.pop(uid, None) is not None

    def in_queue(self, uid: int) -> bool:
        return uid in self.queue

    def partner_of(self, uid: int) -> int | None:
        return self.pairs.get(uid)

    def end_chat(self, uid: int) -> int | None:
        partner = self.pairs.pop(uid, None)
        if partner is not None:
            self.pairs.pop(partner, None)
        return partner

    def active_chats(self) -> int:
        return len(self.pairs) // 2

    def online(self) -> int:
        return sum(1 for u in self.pairs if u > 0) + len(self.queue)

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
