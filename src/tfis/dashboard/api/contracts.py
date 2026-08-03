from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class DashboardApiRouter:
    projection: Mapping[str, Any]

    def resolve(self, path: str) -> tuple[int, dict[str, Any]]:
        normalized = path.rstrip("/") or "/"
        routes = {
            "/api/snapshot.json": lambda: self.projection,
            "/api/system": lambda: self.projection["system"],
            "/api/brokers": self._brokers,
            "/api/accounts": lambda: {"accounts": self.projection["accounts"]},
            "/api/strategy-definitions": self._strategy_definitions,
            "/api/strategy-instances": lambda: {"strategies": self.projection["strategies"]},
            "/api/plans": self._plans,
            "/api/orders": lambda: {"orders": self.projection["orders"]},
            "/api/positions": lambda: {"positions": self.projection["positions"]},
            "/api/carried-positions": self._carried_positions,
            "/api/pnl": self._pnl,
            "/api/analytics": lambda: self.projection["analytics"],
            "/api/alerts": lambda: {"alerts": self.projection["alerts"]},
            "/api/audit": lambda: {"audit": self.projection["audit"]},
            "/api/events": self._events,
            "/api/health": self._health,
        }
        handler = routes.get(normalized)
        if handler is None:
            return 404, {"error": "NOT_FOUND", "path": normalized}
        return 200, dict(handler())

    def _brokers(self) -> dict[str, Any]:
        return {
            "brokers": [
                {
                    "broker": "INTERNAL_PAPER",
                    "status": "AVAILABLE",
                    "order_write_status": "INTERNAL_ONLY",
                },
                {
                    "broker": "FYERS",
                    "status": "READ_ONLY_CONFIGURED",
                    "order_write_status": "NOT_AUTHORIZED",
                },
            ]
        }

    def _strategy_definitions(self) -> dict[str, Any]:
        return {
            "strategy_definitions": sorted(
                {
                    item["identity"]["strategy"]: item["identity"]["version"]
                    for item in self.projection["strategies"]
                }.items()
            )
        }

    def _plans(self) -> dict[str, Any]:
        return {
            "plans": [
                {"identity": item["identity"], "plan": item["plan"], "state": item["state"]}
                for item in self.projection["strategies"]
            ]
        }

    def _carried_positions(self) -> dict[str, Any]:
        return {
            "carried_positions": [
                item for item in self.projection["positions"] if item.get("fresh_or_carried") == "CARRIED"
            ]
        }

    def _pnl(self) -> dict[str, Any]:
        return {
            "realized_pnl": self.projection["command_centre"]["realized_pnl"],
            "unrealized_pnl": self.projection["command_centre"]["unrealized_pnl"],
            "analytics_source": self.projection["analytics"]["source"],
        }

    def _events(self) -> dict[str, Any]:
        return {
            "watermark": self.projection["system"].get("scenario_id"),
            "events": [
                {
                    "event_id": "event:snapshot-ready",
                    "event_type": "SNAPSHOT_READY",
                    "payload_hash": self.projection["projection_hash"],
                }
            ],
            "raw_ticks_included": False,
        }

    def _health(self) -> dict[str, Any]:
        return {
            "status": self.projection["command_centre"]["system_state"],
            "broker_order_authority": self.projection["system"]["broker_order_authority"],
            "projection_hash": self.projection["projection_hash"],
        }
