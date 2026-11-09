"""Offline regression checks: python3 tools/test_capture_test_profiles.py."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import capture_test_profiles as capture
import create_test_profiles as profiles


class FakeSocket:
    def __init__(self, *responses):
        self.data = bytearray()
        self.sent = []
        self.closed = False
        for response in responses:
            data = json.dumps(response).encode()
            self.data.extend(str(len(data)).encode() + b":" + data)

    def settimeout(self, _):
        pass

    def recv(self, size):
        size = min(size, 3)
        data = bytes(self.data[:size])
        del self.data[:size]
        return data

    def sendall(self, data):
        size, payload = data.split(b":", 1)
        assert int(size) == len(payload)
        self.sent.append(json.loads(payload))

    def close(self):
        self.closed = True


class CaptureRegressionTests(unittest.TestCase):
    def test_owned_window_manager_is_closed_when_capture_fails(self):
        process = MagicMock()
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as tmp:
            with (patch.object(capture, "OUTPUT", Path(tmp)),
                  patch.object(capture.subprocess, "check_output", side_effect=[
                      "_NET_SUPPORTING_WM_CHECK: no such atom", "window id # 0x123", '"Openbox"']),
                  patch.object(capture.subprocess, "Popen", return_value=process)):
                with self.assertRaisesRegex(ValueError, "test failure"):
                    with capture.window_manager() as name:
                        self.assertIn("Openbox", name)
                        raise ValueError("test failure")
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)

    def test_denied_context_does_not_retry_session_creation(self):
        transport = FakeSocket(
            {"marionetteProtocol": 3}, [1, 1, None, {}],
            [1, 2, {"error": "unsupported operation", "message": "System access is required"}, None],
        )
        with patch.object(capture.socket, "create_connection", return_value=transport):
            client = capture.Marionette(1234)
        self.assertEqual(transport.sent, [])
        with self.assertRaisesRegex(RuntimeError, "System access is required"):
            client.start_session()
        self.assertEqual([packet[2] for packet in transport.sent],
                         ["WebDriver:NewSession", "Marionette:SetContext"])

    def test_failed_handshake_closes_connection(self):
        transport = FakeSocket()
        with patch.object(capture.socket, "create_connection", return_value=transport):
            with self.assertRaises(ConnectionError):
                capture.Marionette(1234)
        self.assertTrue(transport.closed)

    def test_system_access_is_set_for_the_test_process(self):
        probe = MagicMock()
        probe.__enter__.return_value = probe
        probe.getsockname.return_value = ("127.0.0.1", 1234)
        process = MagicMock()
        process.poll.return_value = 1
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            with patch.object(profiles, "OUTPUT", source):
                profiles.create_profile("blue")
            with (patch.object(capture, "OUTPUT", Path(tmp) / "capture"),
                  patch.object(capture, "SOURCE_PROFILES", source),
                  patch.object(capture.socket, "socket", return_value=probe),
                  patch.object(capture.subprocess, "Popen", return_value=process) as launch,
                  patch.object(capture, "screenshot"),
                  patch("builtins.print")):
                result = capture.capture("blue")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(launch.call_args.kwargs["env"]["MOZ_REMOTE_ALLOW_SYSTEM_ACCESS"], "1")


if __name__ == "__main__":
    unittest.main()
