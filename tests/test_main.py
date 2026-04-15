"""CLI validation tests for runtime mode selection."""

from airdesk.config import AppMode
from airdesk.main import build_arg_parser, validate_args


def test_start_armed_requires_enable_system_actions() -> None:
    """The live backend should not start armed without the explicit safety gate."""
    parser = build_arg_parser()
    args = parser.parse_args(["--mode", AppMode.SYSTEM_MACOS.value, "--start-armed"])

    try:
        validate_args(args, parser)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected --start-armed without --enable-system-actions to fail")
