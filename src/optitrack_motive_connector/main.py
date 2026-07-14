from natnet import *
import context  # Module-level singleton

if __name__ == "__main__":
    # e.g. Start Recording -> 3초간 Log -> Stop Recording -> Flush
    with context.safeguard:
        context.init()
        context.connect()
        context.start_recording()
        context.capture(3)
        context.sleep(2)
        context.stop_recording()
        df = context.to_dataframe()      # Should have 3 second worth of logs
        print(df.head())
        print(df.tail())