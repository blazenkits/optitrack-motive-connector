파이썬 스크립트로 간단하게 Optrack/Motive를 조절할 수 있는 도구입니다.

- Motive의 명령어를 직접 실행할 수 있습니다. (카메라를 직접 켜기, 끄기 etc)

- 판다스 Dataframe로 원하는 시간만큼 캡쳐해 출력할 수 있습니다.

- Dataframe에 기록되는 정보를 직접 설정할 수 있습니다.

### 원리

PC에 설치된 Motive를 서버로 이용해서 NatNet으로 통신합니다.

### 작동 방법 
```python
from optitrack_motive_connector import context


context.init()

with context.safeguard: # 서버 연결이 끊어질 시 자동으로 처리합니다.

    # 서버에 연결합니다.
    context.connect()

    # 녹화를 시작합니다.
    context.start_recording()

    # 3초 동안 정보를 수집하여 로그에 기록합니다.
    context.capture(3)

    # 2초를 더 기다립니다. (정보를 수집하지 않습니다.)
    context.sleep(2)

    # API 명령어를 직접 보낼수도 있습니다.
    context.send_command(...)

    # 녹화를 종료합니다.
    context.stop_recording()

    # 판다스 데이터프레임으로 변환합니다.
    dataframe = context.to_dataframe()
    dataframe.to_csv("capture.csv", index=False)
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
