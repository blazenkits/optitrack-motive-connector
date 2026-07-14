"""
    Module Singleton to store Server Context
"""
from collections.abc import Callable, Iterable
from typing import Any
from natnet import *
import pandas as pd
import time


# A capture function transforms one NatNet frame into zero or more table rows.
CaptureRow = dict[str, Any]
CaptureConfig = Callable[[DataFrame], Iterable[CaptureRow]]

# client singleton
client: NatNetClient | None = None

protocol_version: Version = Version(4, 1)

# 마지막 녹화 정보
records: list[dict] = []
latest_frame: DataFrame | None = None
window_started_at: float | None = None
rigid_body_names: dict[int, str] = {}

_capture_config: CaptureConfig | None = None
_is_capturing = False
# CPU busy loop 방지를 위해 기다릴 시간
PACKET_LISTEN_WAIT = 0.001


class _Safeguard:
    """with 블록을 벗어날 때 NatNet 연결을 안전하게 종료합니다."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        disconnect()
        # with 블록에서 발생한 예외는 숨기지 않습니다.
        return False


safeguard = _Safeguard()

###    외부 API
def init(server_ip_address = "127.0.0.1",
         local_ip_address  = "127.0.0.1",
         use_multicast     = False,
         protocol_version  = (4, 1)
         ):
    """
        서버 설정 및 hook을 연결합니다.
    """
    global client

    client = NatNetClient(server_ip_address=server_ip_address, local_ip_address=local_ip_address, use_multicast=use_multicast)
    client.on_data_description_received_event.handlers.append(_receive_new_desc)
    client.on_data_frame_received_event.handlers.append(_receive_new_frame)
    globals()["protocol_version"] = Version(*protocol_version)

def connect():
    """
        서버에 직접 연결합니다.
    """

    """NatNet 서버에 연결하고 연결 상태를 유지합니다."""
    if client is None:
        raise RuntimeError("먼저 context.init()을 호출해야 합니다.")

    if client.connected:
        return

    client.connect()
    client.protocol_version = protocol_version
    client.request_modeldef()
    print(f"NatNet 버전 {client.protocol_version}")

def disconnect() -> None:
    """NatNet 서버 연결을 종료합니다."""
    if client is not None:
        client.shutdown()

def set_capture_config(capture: CaptureConfig | None) -> None:
    """서버 데이터 (natnet.DataFrame)을 pandas.DataFrame으로 변환시키는 매핑을 반환합니다.

    capture: (natnet.DataFrame) -> list[CaptureRow]를 반환하는 함수입니다.
        CaptureRow는 ["pandas Dataframe 열 이름": "해당 열에 기록될 값"] 입니다.
    """
    global _capture_config

    if capture is not None and not callable(capture):
        raise TypeError("capture config must be callable or None")

    _capture_config = capture


def to_dataframe(clear: bool = True) -> pd.DataFrame:
    """관찰한 결과를 DataFrame으로 반환합니다.

    clear: ``True``이면 DataFrame 생성 후 내부 로그 캐시를 비웁니다. (다음 dataframe()을 호출할때 이 이후부터 시작합니다.)
            같은 로그를 다시 사용하려면 ``False``로 설정합니다.
    """
    captured = pd.DataFrame.from_records(records)

    if clear:
        records.clear()

    return captured

def start_recording():
    '''Motive 서버에 녹화 시작 명령만 전송합니다.'''
    send_command("StartRecording")

def stop_recording():
    '''Motive 서버에 녹화 종료 명령만 전송합니다.'''
    send_command("StopRecording")

def send_command(command: str):
    ''' 서버에 command 직접 보냅니다. Command는 API 참조 '''
    client.send_command(command)


def capture(duration: float) -> None:
    '''UDP 버퍼를 비운 뒤 새로 수신한 프레임을 duration 동안 기록합니다.'''
    global _is_capturing, window_started_at

    if client is None or not client.connected:
        raise RuntimeError("NatNet 서버에 연결되어 있지 않습니다.")
    if duration < 0:
        raise ValueError("duration은 0 이상이어야 합니다.")

    # 기존 UDP 패킷은 hook을 실행해 처리하되 로컬 로그에는 기록하지 않습니다.
    _is_capturing = False
    _drain_pending_packets()

    records.clear()
    window_started_at = None
    _is_capturing = True

    try:
        # 첫 번째 새 프레임의 Motive timestamp를 캡처 시작점으로 사용합니다.
        while window_started_at is None:
            _poll()

        target = window_started_at + duration
        while latest_frame is None or latest_frame.suffix.timestamp < target:
            _poll()
    finally:
        _is_capturing = False


def sleep(duration: float) -> None:
    '''새 프레임을 기록하지 않고 duration 동안 수신하며 기다립니다.'''
    global _is_capturing, window_started_at

    if client is None or not client.connected:
        raise RuntimeError("NatNet 서버에 연결되어 있지 않습니다.")
    if duration < 0:
        raise ValueError("duration은 0 이상이어야 합니다.")

    # 기존 UDP 패킷을 버린 뒤 첫 번째 새 프레임부터 시간을 측정합니다.
    _is_capturing = False
    _drain_pending_packets()
    window_started_at = None

    while window_started_at is None:
        _poll()

    target = window_started_at + duration
    while latest_frame is None or latest_frame.suffix.timestamp < target:
        _poll()


## 내부 API

def _poll() -> None:
    client.update_sync()
    time.sleep(PACKET_LISTEN_WAIT)

# On new description received
def _receive_new_desc(desc: DataDescriptions) -> None:
    """Store the mapping from rigid-body IDs to names."""
    for rigid_body in desc.rigid_bodies:
        rigid_body_names[rigid_body.id_num] = rigid_body.name
        print(
            f"Discovered rigid body: "
            f"id={rigid_body.id_num}, name={rigid_body.name!r}"
        )

# On new frame received
def _receive_new_frame(data_frame: DataFrame) -> None:
    """Convert one NatNet frame into one record per rigid body."""
    global latest_frame, window_started_at

    latest_frame = data_frame

    if window_started_at is None:
        window_started_at = data_frame.suffix.timestamp

    if not _is_capturing:
        return

    capture = _capture_config or _default_capture_config
    records.extend(capture(data_frame))


def _default_capture_config(data_frame: DataFrame) -> list[CaptureRow]:
    """Transform a frame into one long-format row per rigid body."""
    return [
        {
            "frame_number": data_frame.prefix.frame_number,
            "timestamp": data_frame.suffix.timestamp,
            "rigid_body_id": body.id_num,
            "rigid_body_name": rigid_body_names.get(
                body.id_num, f"unknown-{body.id_num}"
            ),
            "x": body.pos[0],
            "y": body.pos[1],
            "z": body.pos[2],
            "qx": body.rot[0],
            "qy": body.rot[1],
            "qz": body.rot[2],
            "qw": body.rot[3],
            "tracking_valid": body.tracking_valid,
            "marker_error": body.marker_error,
        }
        for body in data_frame.rigid_bodies
    ]

def _drain_pending_packets() -> None:
    """현재 UDP 소켓에 대기 중인 패킷을 모두 처리합니다."""
    client.update_sync()
