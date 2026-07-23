import concurrent.futures
import time
import unittest
from types import SimpleNamespace

from natnet import Version

from optitrack_motive_connector import context


class FakeClient:
    def __init__(self, connected=False):
        self.connected = connected
        self.protocol_version = Version(4, 2)
        self.running_asynchronously = False
        self.events = []
        self.update_sync_calls = 0

    def connect(self):
        self.events.append("connect")
        self.connected = True

    def run_async(self):
        self.events.append("run_async")
        self.running_asynchronously = True

    def request_modeldef(self):
        self.events.append("request_modeldef")

    def update_sync(self):
        self.update_sync_calls += 1


def frame(number, timestamp):
    return SimpleNamespace(
        prefix=SimpleNamespace(frame_number=number),
        suffix=SimpleNamespace(timestamp=timestamp),
        rigid_bodies=[],
    )


class ContextAsyncPollingTests(unittest.TestCase):
    def setUp(self):
        self.original_client = context.client
        self.original_capture_config = context._capture_config
        context.latest_frame = None
        context.window_started_at = None
        context._is_capturing = False
        context._capture_ends_at = None
        context._this_capture.clear()

    def tearDown(self):
        context.client = self.original_client
        context._capture_config = self.original_capture_config
        context.latest_frame = None
        context.window_started_at = None
        context._is_capturing = False
        context._capture_ends_at = None
        context._this_capture.clear()

    def test_connect_starts_background_receiver_before_requesting_models(self):
        fake_client = FakeClient()
        context.client = fake_client

        context.connect()

        self.assertEqual(
            fake_client.events,
            ["connect", "run_async", "request_modeldef"],
        )

    def test_capture_does_not_poll_sockets_owned_by_background_receiver(self):
        fake_client = FakeClient(connected=True)
        fake_client.running_asynchronously = True
        context.client = fake_client
        context.set_capture_config(
            lambda data_frame, label: [
                {
                    "frame_number": data_frame.prefix.frame_number,
                    "label": label,
                }
            ]
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            result_future = executor.submit(context.capture, 0.1, "test")
            deadline = time.monotonic() + 1.0
            while not context._is_capturing:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.001)

            context._receive_new_frame(frame(1, 10.0))
            context._receive_new_frame(frame(2, 10.05))
            context._receive_new_frame(frame(3, 10.1))
            result = result_future.result(timeout=1.0)

        self.assertEqual(fake_client.update_sync_calls, 0)
        self.assertEqual(result["frame_number"].tolist(), [1, 2, 3])
        self.assertEqual(result["label"].tolist(), ["test", "test", "test"])


if __name__ == "__main__":
    unittest.main()
