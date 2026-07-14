# OptiTrack Motive Connector

OptiTrack Motive의 NatNet 스트림을 Python에서 수신하고, 실험 구간의 rigid body
6-DoF pose를 pandas `DataFrame`으로 변환하기 위한 프로젝트입니다.

이 프로젝트는 다음 기능을 제공합니다.

- NatNet 서버 연결 및 연결 유지
- Motive 녹화 시작/종료 명령 전송
- 지정한 시간 동안의 로컬 데이터 캡처
- 로그를 남기지 않으면서 NatNet 프레임을 계속 수신하는 대기
- rigid body별 long-format pandas `DataFrame` 생성
- 사용자 정의 frame-to-rows 변환 함수
- `with context.safeguard:`를 이용한 안전한 연결 종료

> 현재 Motive 3.4.0.2에서는 `natnet==0.2.0`과 NatNet 4.1 조합을 사용합니다.
> 연결 방식은 unicast를 권장합니다.

## 설치

이 프로젝트는 [uv](https://docs.astral.sh/uv/)를 사용합니다.

```bash
uv sync
```

## Motive 설정

Motive의 Streaming 설정에서 다음 항목을 확인합니다.

- NatNet Streaming: 활성화
- Transmission Type: Unicast
- Local Interface: Python 클라이언트와 통신할 네트워크 인터페이스
- Command Port: 기본값 `1510`
- Data Port: 기본값 `1511`
- 필요한 데이터 유형(Rigid Bodies 등): 활성화

Motive와 Python 프로그램을 같은 컴퓨터에서 실행한다면 server/local IP로
`127.0.0.1`을 사용할 수 있습니다.

## 기본 사용법

```python
from optitrack_motive_connector import context


context.init(
    server_ip_address="127.0.0.1",
    local_ip_address="127.0.0.1",
    use_multicast=False,
    protocol_version=(4, 1),
)

with context.safeguard:
    context.connect()

    # Motive에 녹화 시작 명령만 전송합니다.
    context.start_recording()

    # 이 3초 동안 수신한 프레임만 로컬 로그에 기록합니다.
    context.capture(3)

    # 프레임은 계속 수신하지만 로컬 로그에는 기록하지 않습니다.
    context.sleep(2)

    # Motive에 녹화 종료 명령만 전송합니다.
    context.stop_recording()

    dataframe = context.to_dataframe()
    dataframe.to_csv("capture.csv", index=False)
```

`context.safeguard` 블록을 정상적으로 벗어나거나 블록 안에서 예외가 발생하면
`context.disconnect()`가 자동으로 호출됩니다. 발생한 예외는 숨기지 않습니다.

## Motive 녹화와 로컬 캡처

Motive 녹화와 로컬 DataFrame 캡처는 서로 독립적입니다.

- `start_recording()`: Motive에 `StartRecording` 명령만 전송
- `stop_recording()`: Motive에 `StopRecording` 명령만 전송
- `capture(duration)`: 해당 구간의 NatNet 프레임을 로컬 로그에 기록
- `sleep(duration)`: 프레임을 수신하고 버리면서 대기

따라서 아래 코드의 DataFrame에는 3초 분량만 포함됩니다.

```python
context.start_recording()
context.capture(3)
context.sleep(2)
context.stop_recording()

dataframe = context.to_dataframe()
```

## 기본 DataFrame 형식

기본 설정에서는 한 행이 한 프레임의 한 rigid body를 나타냅니다.

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

```python
dataframe = context.to_dataframe(clear=False)

for rigid_body_id, body_data in dataframe.groupby("rigid_body_id"):
    print(rigid_body_id)
    print(body_data)
```

## 캡처 형식 사용자 정의

`set_capture_config()`에는 NatNet `DataFrame` 하나를 받고 0개 이상의 행
dictionary를 반환하는 함수를 전달합니다.

```python
from natnet import DataFrame

from optitrack_motive_connector import context


def capture_positions(frame: DataFrame) -> list[dict]:
    return [
        {
            "frame": frame.prefix.frame_number,
            "motive_time": frame.suffix.timestamp,
            "body_id": body.id_num,
            "position": body.pos,
            "is_valid": body.tracking_valid,
        }
        for body in frame.rigid_bodies
    ]


context.set_capture_config(capture_positions)
```

각 dictionary의 key는 pandas DataFrame의 열 이름이 되고, value는 해당 행에
저장됩니다. 빈 iterable을 반환하면 해당 프레임을 기록하지 않습니다.

기본 설정으로 돌아가려면 다음과 같이 호출합니다.

```python
context.set_capture_config(None)
```

## 로그 캐시와 DataFrame 변환

```python
dataframe = context.to_dataframe()
```

`to_dataframe()`의 기본값은 `clear=True`입니다. DataFrame을 만든 뒤 내부 로그
캐시를 비웁니다.

같은 로그를 다시 사용하려면 다음과 같이 호출합니다.

```python
dataframe = context.to_dataframe(clear=False)
```

현재 `capture()`를 새로 호출하면 이전 내부 로그는 초기화됩니다. 여러 구간을
하나의 결과로 합치려면 각 `capture()` 이후 DataFrame을 별도로 보관하고 pandas로
결합해야 합니다.

## 연결 관리

`init()`은 클라이언트 객체와 callback을 구성하지만 실제 연결은 열지 않습니다.
`connect()`가 소켓을 열고, `disconnect()`가 연결을 종료합니다.

```python
context.init()
context.connect()

try:
    context.capture(3)
finally:
    context.disconnect()
```

같은 동작을 `safeguard`로 더 간단하게 작성할 수 있습니다.

```python
context.init()

with context.safeguard:
    context.connect()
    context.capture(3)
```

## UDP 버퍼 처리

NatNet은 UDP를 사용합니다. 연결 중 `capture()` 또는 `sleep()`을 호출하지 않는
동안에도 패킷은 운영체제의 UDP 수신 버퍼에 쌓일 수 있습니다.

`capture()`와 `sleep()`은 시작할 때 기존 패킷을 먼저 처리하여 버립니다.
`capture()`는 그 이후 처음 도착한 프레임의 Motive timestamp부터 시간을 측정하고
로컬 로그를 생성합니다.

UDP 특성상 패킷 전달, 순서, 보존은 보장되지 않습니다. 프레임 누락 여부가 중요한
실험에서는 `frame_number`의 연속성을 함께 검사해야 합니다.

## 현재 제한 사항

- 스트리밍이 중단되면 `capture()`와 `sleep()`이 계속 기다릴 수 있습니다.
- 한 번의 `update_sync()`가 여러 패킷을 처리하므로 목표 timestamp를 조금 넘는
  마지막 프레임이 포함될 수 있습니다.
- `start_recording()`과 `stop_recording()`은 명령 전송만 수행하며 Motive의 실제
  상태 변경을 확인하지 않습니다.
- 정밀한 외부 장비 동기화가 필요하면 Python/UDP 명령 대신 hardware trigger,
  timecode 또는 OptiTrack 동기화 장비를 사용해야 합니다.

## 주요 API

| 함수 | 설명 |
|---|---|
| `init(...)` | NatNet 클라이언트와 callback 설정 |
| `connect()` | 서버에 연결하고 연결 유지 |
| `disconnect()` | 서버 연결 종료 |
| `start_recording()` | Motive 녹화 시작 명령 전송 |
| `stop_recording()` | Motive 녹화 종료 명령 전송 |
| `capture(duration)` | 새 프레임을 지정 시간 동안 로컬 로그에 기록 |
| `sleep(duration)` | 새 프레임을 기록하지 않고 지정 시간 동안 수신 |
| `set_capture_config(fn)` | frame-to-rows 변환 함수 설정 |
| `to_dataframe(clear=True)` | 로그를 pandas DataFrame으로 변환 |
| `send_command(command)` | 임의의 NatNet command 전송 |
