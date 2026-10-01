"""The CLI must close durable resources when serving stops or startup fails."""

from __future__ import annotations

from io import StringIO
from unittest import TestCase
from unittest.mock import Mock, patch

from symphonia import __main__ as cli


class RuntimeCLITests(TestCase):
    def test_sigterm_stop_closes_listener_and_resources_then_restores_handler(self) -> None:
        server = Mock()
        server.serve_forever.side_effect = KeyboardInterrupt
        previous_handler = object()

        with (
            patch("sys.argv", ["symphonia", "--port", "8100"]),
            patch.object(cli.signal, "signal", return_value=previous_handler) as install_signal,
            patch.object(cli, "create_server", return_value=server) as create_server,
        ):
            cli.main()

        create_server.assert_called_once_with("127.0.0.1", 8100, "./symphonia.sqlite3", "/")
        server.server_close.assert_called_once_with()
        server.close_resources.assert_called_once_with()
        self.assertEqual(install_signal.call_args_list[-1].args, (cli.signal.SIGTERM, previous_handler))

    def test_server_start_failure_restores_previous_signal_handler(self) -> None:
        previous_handler = object()
        with (
            patch("sys.argv", ["symphonia"]),
            patch.object(cli.signal, "signal", return_value=previous_handler) as install_signal,
            patch.object(cli, "create_server", side_effect=OSError("bind failed")),
        ):
            with self.assertRaisesRegex(OSError, "bind failed"):
                cli.main()

        self.assertEqual(install_signal.call_args_list[-1].args, (cli.signal.SIGTERM, previous_handler))

    def test_resource_close_is_attempted_even_if_listener_close_fails(self) -> None:
        server = Mock()
        server.serve_forever.side_effect = KeyboardInterrupt
        server.server_close.side_effect = OSError("close failed")
        with (
            patch("sys.argv", ["symphonia"]),
            patch.object(cli.signal, "signal", return_value=object()),
            patch.object(cli, "create_server", return_value=server),
        ):
            with self.assertRaisesRegex(OSError, "close failed"):
                cli.main()

        server.close_resources.assert_called_once_with()

    def test_invalid_configuration_never_opens_resources_or_changes_signals(self) -> None:
        with (
            patch("sys.argv", ["symphonia", "--port", "0"]),
            patch("sys.stderr", new_callable=StringIO),
            patch.object(cli.signal, "signal") as install_signal,
            patch.object(cli, "create_server") as create_server,
        ):
            with self.assertRaises(SystemExit) as exit_status:
                cli.main()

        self.assertEqual(exit_status.exception.code, 2)
        install_signal.assert_not_called()
        create_server.assert_not_called()
