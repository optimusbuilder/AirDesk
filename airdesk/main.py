"""Command-line entry point for the AirDesk prototype."""

from argparse import ArgumentParser, Namespace
from dataclasses import replace
from typing import Sequence

from airdesk.app import AirDeskApp
from airdesk.config import AppConfig, AppMode, build_default_config


def build_arg_parser() -> ArgumentParser:
    """Return the CLI parser for the AirDesk app."""
    parser = ArgumentParser(
        description="Launch the AirDesk prototype, shadow mode, or live macOS control."
    )
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in AppMode],
        default=AppMode.PROTOTYPE.value,
        help="Choose the runtime mode.",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=None,
        help="Override the webcam device index.",
    )
    parser.add_argument(
        "--enable-system-actions",
        action="store_true",
        help="Allow real system actions when running in live macOS mode.",
    )
    parser.add_argument(
        "--start-armed",
        action="store_true",
        help="Start live macOS mode armed instead of waiting for the S toggle.",
    )
    debug_hud_group = parser.add_mutually_exclusive_group()
    debug_hud_group.add_argument(
        "--show-debug-hud",
        action="store_true",
        help="Force the on-screen debug HUD to be visible.",
    )
    debug_hud_group.add_argument(
        "--hide-debug-hud",
        action="store_true",
        help="Hide the on-screen debug HUD for a cleaner demo view.",
    )
    return parser


def validate_args(args: Namespace, parser: ArgumentParser) -> None:
    """Validate CLI combinations that affect safety-critical system control."""
    if args.enable_system_actions and args.mode != AppMode.SYSTEM_MACOS.value:
        parser.error("--enable-system-actions is only supported with --mode system-macos")
    if args.start_armed and args.mode != AppMode.SYSTEM_MACOS.value:
        parser.error("--start-armed requires --mode system-macos")
    if args.start_armed and not args.enable_system_actions:
        parser.error("--start-armed requires --enable-system-actions")


def build_config_from_args(args: Namespace) -> AppConfig:
    """Apply supported CLI overrides to the default app config."""
    config = build_default_config()
    config = replace(
        config,
        system=replace(
            config.system,
            mode=AppMode(args.mode),
            enable_live_backend=args.enable_system_actions,
            start_armed=args.start_armed,
        ),
    )

    if args.camera_index is not None:
        config = replace(
            config,
            camera=replace(config.camera, device_index=args.camera_index),
        )

    if args.show_debug_hud:
        config = replace(
            config,
            render=replace(config.render, show_debug_hud=True),
        )
    elif args.hide_debug_hud:
        config = replace(
            config,
            render=replace(config.render, show_debug_hud=False),
        )

    return config


def main(argv: Sequence[str] | None = None) -> int:
    """Launch the AirDesk application."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    validate_args(args, parser)
    app = AirDeskApp(config=build_config_from_args(args))
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
