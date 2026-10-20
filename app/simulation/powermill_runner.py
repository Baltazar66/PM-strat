from __future__ import annotations

from typing import List, Dict


class PowerMillRunner:
    def __init__(self, settings) -> None:
        self.settings = settings

    def prepare_simulation(self, strategies: List[object]) -> Dict[str, object]:
        return {
            "status": "ready",
            "strategies_count": len(strategies),
            "message": "Simulation package prepared. Attach real PowerMill bridge to run execution.",
        }

    def launch_post_processing(self) -> Dict[str, object]:
        return {
            "status": "not_started",
            "message": "PowerMill post-processing is not active because bridge is not configured.",
        }
