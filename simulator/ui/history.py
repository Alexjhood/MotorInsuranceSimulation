from __future__ import annotations

from typing import Dict, List, Tuple


class ServerSideHistory:
    """Server-side storage for simulation history to avoid browser memory issues."""

    def __init__(self, max_entries: int = 100):
        self.max_entries = max_entries
        self._history: List[Dict] = []
        self._index: int = 0

    def append(self, state: Dict, accidents: List) -> int:
        """Append a new history entry, returns new index."""
        if self._index < len(self._history) - 1:
            self._history = self._history[: self._index + 1]

        self._history.append({"state": state, "accidents": accidents})

        if len(self._history) > self.max_entries:
            self._history = self._history[-self.max_entries :]

        self._index = len(self._history) - 1
        return self._index

    def go_back(self) -> Tuple[Dict, List, int]:
        """Go back one step, returns (state, accidents, new_index) or None if can't go back."""
        if self._index > 0:
            self._index -= 1
            entry = self._history[self._index]
            return entry["state"], entry["accidents"], self._index
        return None, None, self._index

    def get_current(self) -> Tuple[Dict, List, int]:
        """Get current history entry."""
        if self._history:
            entry = self._history[self._index]
            return entry["state"], entry["accidents"], self._index
        return None, [], 0

    def reset(self):
        """Clear all history."""
        self._history = []
        self._index = 0

    @property
    def index(self) -> int:
        return self._index

    @property
    def length(self) -> int:
        return len(self._history)


server_history = ServerSideHistory(max_entries=50)
