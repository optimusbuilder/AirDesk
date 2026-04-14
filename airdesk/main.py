"""Command-line entry point for the AirDesk prototype."""

from airdesk.app import AirDeskApp


def main() -> int:
    """Launch the AirDesk application."""
    app = AirDeskApp()
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
