"""Server-side simulation cache to avoid expensive serialization/deserialization.

The main bottleneck is that deserialize_sim() creates a new Simulation object,
which regenerates the entire map from scratch (5-6 seconds for large maps).

This module caches the Simulation object server-side, so we only serialize
the state for client-side storage but use the cached object for actual simulation.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from simulator.engine.simulation import Simulation

logger = logging.getLogger(__name__)


class RenderGate:
    """Gate to coordinate advance and render callbacks.
    
    Ensures we don't advance to the next step until the previous step
    has been rendered. This prevents Dash from coalescing state updates
    and skipping intermediate steps.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._pending_render_step: Optional[int] = None
        self._pending_since: float = 0  # When step was marked pending
    
    def step_completed(self, step: int) -> None:
        """Called when advance completes a step - marks it as pending render."""
        with self._lock:
            self._pending_render_step = step
            self._pending_since = time.time()
            logger.debug(f"[RENDER_GATE] Step {step} completed, pending render")
    
    def render_completed(self, step: int) -> None:
        """Called when render finishes - clears the pending flag."""
        with self._lock:
            if self._pending_render_step == step:
                self._pending_render_step = None
                self._pending_since = 0
            logger.debug(f"[RENDER_GATE] Step {step} rendered")
    
    def can_advance(self) -> bool:
        """Check if we can start a new advance (no pending render)."""
        with self._lock:
            if self._pending_render_step is not None:
                # Allow advance if render has been pending too long (timeout)
                elapsed = time.time() - self._pending_since
                if elapsed > 10.0:  # 10 second timeout (increased from 5)
                    logger.warning(f"[RENDER_GATE] Render timeout for step {self._pending_render_step} after {elapsed:.1f}s, allowing advance")
                    self._pending_render_step = None
                    self._pending_since = 0
                    return True
                logger.debug(f"[RENDER_GATE] Blocking advance - step {self._pending_render_step} pending render for {elapsed:.1f}s")
                return False
            return True
    
    def get_pending_step(self) -> Optional[int]:
        """Get the step number pending render, if any."""
        with self._lock:
            return self._pending_render_step


# Global singleton for render coordination
render_gate = RenderGate()


class SimulationCache:
    """Thread-safe cache for the current simulation object.
    
    Instead of deserializing the full state each callback (which recreates
    the map), we keep the Simulation object in memory and only use the
    serialized state for history/recovery.
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._simulation: Optional[Simulation] = None
        self._step_index: int = -1
        self._config_hash: Optional[int] = None
    
    def get(self) -> Optional[Simulation]:
        """Get the cached simulation if available."""
        with self._lock:
            return self._simulation
    
    def set(self, simulation: Simulation) -> None:
        """Cache a simulation object."""
        with self._lock:
            self._simulation = simulation
            self._step_index = simulation.step_index
            self._config_hash = self._hash_config(simulation.config)
            logger.info(f"[SIM_CACHE] Cached simulation at step {self._step_index}")
    
    def clear(self) -> None:
        """Clear the cache (e.g., when config changes)."""
        with self._lock:
            self._simulation = None
            self._step_index = -1
            self._config_hash = None
            logger.info("[SIM_CACHE] Cache cleared")
    
    def is_valid_for(self, state: dict) -> bool:
        """Check if cached simulation can be used for this state.
        
        We only check if the config matches - the cached simulation IS the
        authoritative state. The incoming state may be stale (from the client)
        but our cached simulation is always up-to-date.
        """
        with self._lock:
            if self._simulation is None:
                return False
            
            # Only check config matches - step index will differ because
            # the client state lags behind the server cache
            config_data = state.get("config", {})
            state_hash = self._hash_config_data(config_data)
            if state_hash != self._config_hash:
                logger.debug("[SIM_CACHE] Config mismatch - cache invalid")
                return False
            
            # Log the step difference for debugging
            state_step = state.get("step_index", -1)
            if state_step != self._step_index:
                logger.debug(f"[SIM_CACHE] Using cache (step {self._step_index}) despite stale client state (step {state_step})")
            
            return True
    
    def _hash_config(self, config) -> int:
        """Create a hash of the config for comparison."""
        from dataclasses import asdict
        config_dict = asdict(config)
        return hash(str(sorted(config_dict.items())))
    
    def _hash_config_data(self, config_data: dict) -> int:
        """Create a hash from config dict."""
        return hash(str(sorted(config_data.items())))


# Global singleton
simulation_cache = SimulationCache()
