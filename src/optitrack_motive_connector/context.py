"""
    Module Singleton to store Server Context
"""
import functools
import inspect
import threading
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from natnet import *
import pandas as pd
import time


# A capture function transforms one NatNet frame into zero or more table rows.
CaptureRow = dict[str, Any]
CaptureConfig = Callable[[DataFrame, str], Iterable[CaptureRow]]

# client singleton
client: NatNetClient | None = None

protocol_version: Version = Version(4, 1)

# 지금까지의 녹화 정보
latest_frame: DataFrame | None = None
window_started_at: float | None = None
rigid_body_names: dict[int, str] = {}

_capture_config: CaptureConfig | None = None
_is_capturing = False
_capture_ends_at: float | None = None
_capture_duration = 0.0
_stream_operation_lock = threading.Lock()
# CPU busy loop 방지를 위해 기다릴 시간
PACKET_LISTEN_WAIT = 0.001
DEFAULT_FRAME_TIMEOUT = 5.0


### ========== Utilities =============== ###
class _Connection:
    """with 블록을 벗어날 때 NatNet 연결을 안전하게 종료합니다."""

    def __enter__(self) -> "_Connection":
        try:
            connect()
        except BaseException:
            # __enter__에서 예외가 발생하면 __exit__은 호출되지 않습니다.
            try:
                disconnect()
            except Exception:
                pass
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        disconnect()
        # with 블록에서 발생한 예외는 숨기지 않습니다.
        return False

# with connection ... 호출을 위해서
connection = _Connection()


# Client 연결 필요 Decorator
def requires_connection(fn):
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        if client is None or not client.connected:
            raise RuntimeError("NatNet 서버에 연결되어 있지 않습니다.")
        return fn(*args, **kwargs)
    return inner

###  ========== 외부 API =========== ###

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

    if capture is not None:
        try:
            inspect.signature(capture).bind(None, "")
        except (TypeError, ValueError) as error:
            raise TypeError(
                "capture config must accept (data_frame, capture_label)"
            ) from error

    _capture_config = capture



def start_recording():
    '''Motive 서버에 녹화 시작 명령만 전송합니다.'''
    send_command("StartRecording")

def stop_recording():
    '''Motive 서버에 녹화 종료 명령만 전송합니다.'''
    send_command("StopRecording")

@requires_connection
def send_command(command: str):
    ''' 서버에 command 직접 보냅니다. Command는 API 참조 '''
    client.send_command(command)    # type:ignore

@requires_connection
def capture(
    duration: float,
    capture_label: str = "",
    frame_timeout: float = DEFAULT_FRAME_TIMEOUT,
) -> pd.DataFrame:
    '''UDP 버퍼를 비운 뒤 새로 수신한 프레임을 duration 동안 기록합니다.
        duration: 녹화할 시간 (초)
        capture_label: 이 녹화에 대한 레이블
    '''
    global _is_capturing, window_started_at, _this_capture, _capture_label
    global _capture_duration, _capture_ends_at

    if duration < 0:
        raise ValueError("duration은 0 이상이어야 합니다.")
    if frame_timeout <= 0:
        raise ValueError("frame_timeout은 0보다 커야 합니다.")
    if not _stream_operation_lock.acquire(blocking=False):
        raise RuntimeError("다른 capture() 또는 sleep()이 이미 실행 중입니다.")

    try:
        # 기존 UDP 패킷은 hook을 실행해 처리하되 로컬 로그에는 기록하지 않습니다.
        _drain_pending_packets()
        _this_capture.clear()
        window_started_at = None
        _capture_ends_at = None
        _capture_duration = duration
        _capture_label = capture_label
        _is_capturing = True

        # 첫 번째 새 프레임의 Motive timestamp를 캡처 시작점으로 사용합니다.
        _poll_until(lambda: window_started_at is not None, frame_timeout)

        target = _capture_ends_at
        assert target is not None
        _poll_until(
            lambda: latest_frame is not None
            and latest_frame.suffix.timestamp >= target,
            frame_timeout,
        )

        return pd.DataFrame.from_records(_this_capture)
    finally:
        _is_capturing = False
        _capture_ends_at = None
        _stream_operation_lock.release()


@requires_connection
def sleep(
    duration: float,
    frame_timeout: float = DEFAULT_FRAME_TIMEOUT,
) -> None:
    '''새 프레임을 기록하지 않고 duration 동안 수신하며 기다립니다.'''
    global _is_capturing, window_started_at

    if duration < 0:
        raise ValueError("duration은 0 이상이어야 합니다.")
    if frame_timeout <= 0:
        raise ValueError("frame_timeout은 0보다 커야 합니다.")
    if not _stream_operation_lock.acquire(blocking=False):
        raise RuntimeError("다른 capture() 또는 sleep()이 이미 실행 중입니다.")

    try:
        # 기존 UDP 패킷을 버린 뒤 첫 번째 새 프레임부터 시간을 측정합니다.
        _drain_pending_packets()
        _is_capturing = False
        window_started_at = None

        _poll_until(lambda: window_started_at is not None, frame_timeout)

        target = window_started_at + duration
        _poll_until(
            lambda: latest_frame is not None
            and latest_frame.suffix.timestamp >= target,
            frame_timeout,
        )
    finally:
        _is_capturing = False
        _stream_operation_lock.release()

### ================= Utility ====================
def get_rigidbody_name(rigid_body_id) -> str | None:
    '''
    rigid_body_id: DataFrame.rigidbodies.id_num
    이름을 못 찾으면 None을 반환함.
    '''
    return rigid_body_names.get(rigid_body_id, None)


### ================= 내부 API ===================

_this_capture: list[CaptureRow] = []
_capture_label = ""
@requires_connection
def _poll() -> None:
    client.update_sync() #type:ignore
    time.sleep(PACKET_LISTEN_WAIT)


def _poll_until(condition: Callable[[], bool], frame_timeout: float) -> None:
    """조건을 기다리되 새 프레임이 frame_timeout 동안 없으면 실패합니다."""
    previous_frame_number = (
        latest_frame.prefix.frame_number if latest_frame is not None else None
    )
    deadline = time.monotonic() + frame_timeout

    while not condition():
        _poll()

        current_frame_number = (
            latest_frame.prefix.frame_number if latest_frame is not None else None
        )
        if current_frame_number != previous_frame_number:
            previous_frame_number = current_frame_number
            deadline = time.monotonic() + frame_timeout
        elif time.monotonic() >= deadline:
            raise TimeoutError(
                f"{frame_timeout}초 동안 새 NatNet 프레임을 받지 못했습니다."
            )

# On new description received
def _receive_new_desc(desc: DataDescriptions) -> None:
    """Store the mapping from rigid-body IDs to names."""
    for rigid_body in desc.rigid_bodies:
        rigid_body_names[rigid_body.id_num] = rigid_body.name # type: ignore
        print(
            f"Discovered rigid body: "
            f"id={rigid_body.id_num}, name={rigid_body.name!r}"
        )

# On new frame received
def _receive_new_frame(data_frame: DataFrame) -> None:
    """Convert one NatNet frame into one record per rigid body."""
    global latest_frame, window_started_at, _capture_ends_at

    latest_frame = data_frame

    if window_started_at is None:
        window_started_at = data_frame.suffix.timestamp

    if not _is_capturing:
        return

    if _capture_ends_at is None:
        _capture_ends_at = window_started_at + _capture_duration

    # update_sync()가 여러 패킷을 처리해도 목표 시각 이후의 프레임은 기록하지 않습니다.
    if data_frame.suffix.timestamp > _capture_ends_at:
        return

    capture = _capture_config or _default_capture_config
    parsed = capture(data_frame, _capture_label)
    _this_capture.extend(_validate_capture_rows(parsed))


def _validate_capture_rows(rows: Iterable[CaptureRow]) -> list[CaptureRow]:
    """사용자 capture config의 반환값을 검증하고 독립된 row로 복사합니다."""
    if isinstance(rows, Mapping) or isinstance(rows, (str, bytes)):
        raise TypeError("capture config must return an iterable of row mappings")

    try:
        iterator = iter(rows)
    except TypeError as error:
        raise TypeError(
            "capture config must return an iterable of row mappings"
        ) from error

    validated: list[CaptureRow] = []
    for index, row in enumerate(iterator):
        if not isinstance(row, Mapping):
            raise TypeError(
                f"capture config row {index} must be a mapping, "
                f"got {type(row).__name__}"
            )
        validated.append(dict(row))

    return validated


def _default_capture_config(data_frame: DataFrame, capture_label: str) -> list[CaptureRow]:
    """수집된 데이터를 판다스 데이터프레임의 row들로 변환하는 함수입니다.

        data_frame (NatNet.DataFrame): 수집된 정보
        capture_label: 현재 캡쳐에 해당하는 레이블

        returns: 각 원소가 dictionary로서 판다스 데이터프레임의 한 row에 해당하는 리스트
        e.g. [
            {x: "foo1", y: "bar1"},
            {x: "foo2", y: "bar2"}
        ]

        기본적으로 한 행에 Body정보 [
            {label: "...", body: "Body1"}
            {label: "...", body: "Body2"}
            {label: "...", body: "Body3"}
            ...
        ] 를 반환합니다.
    """

    return [
        {
            "frame_number": data_frame.prefix.frame_number,
            "label" : capture_label,
            "timestamp": data_frame.suffix.timestamp,
            "rigid_body_id": body.id_num,
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

@requires_connection
def _drain_pending_packets() -> None:
    """현재 UDP 소켓에 대기 중인 패킷을 모두 처리합니다."""
    global _is_capturing
    _was_capturing = _is_capturing
    _is_capturing = False
    try:
        client.update_sync() # type: ignore
    finally:
        _is_capturing = _was_capturing
