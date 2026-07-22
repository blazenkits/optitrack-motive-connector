## Optitrack Motive Connector

파이썬 스크립트로 간단하게 Optrack/Motive를 조절할 수 있는 도구입니다.
- Motive의 명령어를 직접 실행할 수 있습니다. (녹화 시작, 종료 etc)

- 판다스 Dataframe로 원하는 시간만큼 캡쳐해 출력할 수 있습니다.

- Dataframe에 기록되는 정보를 직접 설정할 수 있습니다.

### 원리

PC에 설치된 Motive를 서버로 이용해서 NatNet으로 통신합니다.

### 작동 방법 
```python
# 3초간 녹화를 998번 반복하는 스크립트
from optitrack_motive_connector import context
from pandas import DataFrame
import pandas as pd

if __name__ == "__main__":
    
    records = []

    context.init(
        server_ip_address= "127.0.0.1",
        local_ip_address = "127.0.0.1"
    )    # 기본 세팅

    with context.connection:
        context.start_recording()           # 녹화 시작

        for capture_label in range(1, 999): # 반복

            print(f"Starting capture {capture_label}")

            capture: DataFrame = context.capture(3.0, f"Capture {capture_label}")  # 3초동안 데이터를 기록하고 DataFrame로 반환

            records.append(                
                capture.groupby(["label", "rigid_body_id"]).agg(      
                    average_x=("x", "mean"),
                    average_y=("y", "mean"),
                    average_z=("z", "mean"),
                    )
            )   # 3초간 데이터의 RigidBody당 평균 위치를 기록
            
            context.sleep(2)    # 2초동안 수면

        
        context.stop_recording()  # 녹화 종료
        df = pd.concat(records)   # 최종 DataFrame 생성
```
## 설치

uv를 사용하면
```bash
uv sync
```
또는 기본 파이썬에 `natnet`, `pandas` 패키지를 설치하면 됩니다.

## Motive 설정

Edit -> Settings -> NatNet -> Enable

- 로컬 실행시 Local Interface: Loopback / Transmission Type: Unicast

Live Mode에서 진행해야 합니다. (Edit Mode에서는 프레임을 송신하지 않습니다.)

Motive 3.4.0.2는 NatNet 4.2를 사용합니다.

## 기본 DataFrame 형식

현재 설정에서는 한 행이 한 프레임의 한 rigid body를 나타냅니다.

| 열 | 설명 |
|---|---|
| `frame_number` | Motive 프레임 번호 |
| `timestamp` | Motive 프레임 timestamp |
| `rigid_body_id` | rigid body 숫자 ID |
| `rigid_body_name` | model description에서 받은 이름 |
| `x`, `y`, `z` | 위치 |
| `qx`, `qy`, `qz`, `qw` | orientation quaternion |
| `tracking_valid` | Motive의 추적 유효 여부 |
| `marker_error` | rigid body marker error |

여러 rigid body가 있다면 같은 `frame_number`와 `timestamp`를 가진 행이 rigid
body별로 생성됩니다.

DataFrame 파싱 방법을 직접 `set_capture_config()`에서 정의할 수 있습니다.
