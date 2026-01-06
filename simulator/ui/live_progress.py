"""Server-side progress store for real-time simulation progress tracking.

This module provides a thread-safe store that the simulation can update
as it progresses through phases, and the UI can poll to show live updates.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class PhaseProgress:
    """Progress information for a single simulation phase."""
    name: str
    total: int = 0
    completed: int = 0
    duration_ms: float = 0.0
    state: str = "pending"  # pending, running, complete, error
    summary: Dict = field(default_factory=dict)
    items: List[Dict] = field(default_factory=list)
    truncated: int = 0
    note: str = ""
    
    @property
    def progress_pct(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100
    
    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "total": self.total,
            "completed": self.completed,
            "duration_ms": self.duration_ms,
            "progress_pct": self.progress_pct,
            "state": self.state,
        }
        if self.summary:
            result["summary"] = self.summary
        if self.items:
            result["items"] = self.items
        if self.truncated > 0:
            result["truncated"] = self.truncated
        if self.note:
            result["note"] = self.note
        return result


@dataclass
class LiveProgress:
    """Live progress state for a simulation step."""
    step: int = 0
    status: str = "idle"  # idle, running, complete, error
    current_phase: str = ""
    started_at: float = 0.0
    phases: Dict[str, PhaseProgress] = field(default_factory=dict)
    stats: Dict = field(default_factory=dict)
    error: str = ""
    total_ms: float = 0.0
    
    def to_dict(self) -> dict:
        # Order phases by definition order
        phase_order = [
            "Agent movement",
            "Lane assignment",
            "Occupancy tally",
            "Unilateral accident checks",
            "Multi-agent accident checks",
            "Event + accident logging",
        ]
        ordered_phases = []
        for name in phase_order:
            if name in self.phases:
                ordered_phases.append(self.phases[name].to_dict())
        # Add any extra phases not in the predefined order
        for name, phase in self.phases.items():
            if name not in phase_order:
                ordered_phases.append(phase.to_dict())
        
        result = {
            "step": self.step,
            "status": self.status,
            "current_phase": self.current_phase,
            "started_at": self.started_at,
            "phases": ordered_phases,
            "stats": self.stats,
            "total_ms": self.total_ms,
        }
        if self.error:
            result["error"] = self.error
        return result


class LiveProgressStore:
    """Thread-safe store for live simulation progress.
    
    This allows the simulation (potentially in a background thread) to update
    progress, while the UI can poll for updates independently.
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._progress: Optional[LiveProgress] = None
        self._version: int = 0
        self._last_update: float = 0.0
    
    def start_step(self, step: int, stats: Dict = None) -> None:
        """Called when a new simulation step begins."""
        with self._lock:
            self._progress = LiveProgress(
                step=step,
                status="running",
                started_at=time.time(),
                stats=stats or {},
            )
            self._version += 1
            self._last_update = time.time()
    
    def start_phase(self, name: str, total: int = 0) -> None:
        """Called when a phase starts."""
        with self._lock:
            if self._progress is None:
                return
            self._progress.current_phase = name
            self._progress.phases[name] = PhaseProgress(
                name=name,
                total=total,
                state="running",
            )
            self._version += 1
            self._last_update = time.time()
    
    def update_phase(
        self,
        name: str,
        completed: int = None,
        total: int = None,
        duration_ms: float = None,
        items: List[Dict] = None,
        truncated: int = None,
        summary: Dict = None,
        note: str = None,
    ) -> None:
        """Update progress for a phase (can be called multiple times during execution)."""
        with self._lock:
            if self._progress is None:
                return
            phase = self._progress.phases.get(name)
            if phase is None:
                phase = PhaseProgress(name=name, state="running")
                self._progress.phases[name] = phase
            
            if completed is not None:
                phase.completed = completed
            if total is not None:
                phase.total = total
            if duration_ms is not None:
                phase.duration_ms = duration_ms
            if items is not None:
                phase.items = items
            if truncated is not None:
                phase.truncated = truncated
            if summary is not None:
                phase.summary = summary
            if note is not None:
                phase.note = note
            
            self._version += 1
            self._last_update = time.time()
    
    def complete_phase(
        self,
        name: str,
        total: int,
        completed: int,
        duration_ms: float,
        items: List[Dict] = None,
        truncated: int = None,
        summary: Dict = None,
        note: str = None,
    ) -> None:
        """Mark a phase as complete with final stats."""
        with self._lock:
            if self._progress is None:
                return
            phase = self._progress.phases.get(name)
            if phase is None:
                phase = PhaseProgress(name=name)
                self._progress.phases[name] = phase
            
            phase.total = total
            phase.completed = completed
            phase.duration_ms = duration_ms
            phase.state = "complete"
            if items is not None:
                phase.items = items
            if truncated is not None:
                phase.truncated = truncated
            if summary is not None:
                phase.summary = summary
            if note is not None:
                phase.note = note
            
            self._version += 1
            self._last_update = time.time()
    
    def complete_step(self, total_ms: float, accident_count: int = 0) -> None:
        """Called when the simulation step completes successfully."""
        with self._lock:
            if self._progress is None:
                return
            self._progress.status = "complete"
            self._progress.current_phase = "completed"
            self._progress.total_ms = total_ms
            if "accident_count" not in self._progress.stats:
                self._progress.stats["accident_count"] = accident_count
            self._version += 1
            self._last_update = time.time()
    
    def error_step(self, error: str, failed_phase: str = None) -> None:
        """Called when an error occurs during the step."""
        with self._lock:
            if self._progress is None:
                return
            self._progress.status = "error"
            self._progress.error = error
            if failed_phase and failed_phase in self._progress.phases:
                self._progress.phases[failed_phase].state = "error"
            self._version += 1
            self._last_update = time.time()
    
    def clear(self) -> None:
        """Clear the progress store."""
        with self._lock:
            self._progress = None
            self._version += 1
            self._last_update = time.time()
    
    def get_progress(self) -> Optional[dict]:
        """Get current progress as a dictionary (for UI consumption)."""
        with self._lock:
            if self._progress is None:
                return None
            return self._progress.to_dict()
    
    def get_version(self) -> int:
        """Get the current version number (for change detection)."""
        with self._lock:
            return self._version
    
    def get_if_changed(self, last_version: int) -> tuple[Optional[dict], int]:
        """Get progress only if it has changed since last_version.
        
        Returns (progress_dict or None, current_version).
        """
        with self._lock:
            if self._version == last_version:
                return None, self._version
            if self._progress is None:
                return None, self._version
            return self._progress.to_dict(), self._version


# Global singleton instance
live_progress_store = LiveProgressStore()
