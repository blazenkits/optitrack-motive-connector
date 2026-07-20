from pandas import DataFrame
import pandas as pd
from natnet import DataFrame as NatNetDataFrame
from optitrack_motive_connector import context  # Module-level singleton


def custom_capture_config(data_frame: NatNetDataFrame, capture_label: str):
    # 예시로 위치만 추적하는 config
    return [
            {
                "label" : capture_label,
                "rigid_body_id": body.id_num,
                "x": body.pos[0],
                "y": body.pos[1],
                "z": body.pos[2],
                "tracking_valid": body.tracking_valid,
                "marker_error": body.marker_error,
            } for body in data_frame.rigid_bodies
        ]

if __name__ == "__main__":
    
    records = []    # DataFrame들을 담을 공간

    context.init(
        server_ip_address= "127.0.0.1",
        local_ip_address = "127.0.0.1"
    )                                                   # 기본 세팅

    context.set_capture_config(custom_capture_config)   # 어떤 데이터를 수집할지

    with context.connection:
        context.start_recording()                   # 녹화 시작

        for capture_label in range(1, 101):

            print(f"Starting capture {capture_label}")

            capture: DataFrame = context.capture(3.0, f"Capture {capture_label}")   # 3초동안 기록

            records.append(
                capture.groupby(["label", "rigid_body_id"]).agg(       # 그 3초동안 mean을 구한 데이터프레임을 저장함
                    average_x=("x", "mean"),
                    average_y=("y", "mean"),
                    average_z=("z", "mean"),
                    )
            )
            
            context.sleep(2)    # 2초동안 수면 (time.sleep()하면 UDP queue 처리때문에 랙이 발생할 수 있으므로 context.sleep()하는 것이 좋습니다.)

        
        context.stop_recording()
        df = pd.concat(records)
        print(df.iloc[0])
        print(df.iloc[-1])
        df.to_csv("capture.csv")