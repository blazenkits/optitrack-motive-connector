from natnet import *
import context  # Module-level singleton

if __name__ == "__main__":
    # e.g. Start Recording -> 3초간 Log -> Stop Recording -> Flush
    with context.safeguard:
        context.init()
        context.set_capture_config(...)
        context.connect()
        context.start_recording()
        context.capture(3)
        context.sleep(2)
        context.stop_recording()
        context.to_dataframe()      # Should have 3 second worth of logs