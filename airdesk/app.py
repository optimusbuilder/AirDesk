"""Application shell for the AirDesk prototype."""

from dataclasses import dataclass, field

from airdesk.config import AppConfig, build_default_config


@dataclass(slots=True)
class AirDeskApp:
    """Top-level application wrapper for future runtime orchestration."""

    config: AppConfig = field(default_factory=build_default_config)

    def run(self) -> int:
        """Start the application.

        The actual runtime loop will be implemented incrementally, beginning
        with the camera baseline in Milestone 1.
        """
        print("AirDesk scaffold ready. Begin Milestone 1 implementation from the README plan.")
        return 0
