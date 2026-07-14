from natnet import *
import time

SERVER_IP = "127.0.0.1"
LOCAL_IP  = "127.0.0.1"
PROTOCOL_VERSION = Version(4, 1)    # 설치된 Motive 3.4.0.2에 맞는 설정입니다.

def receive_new_desc(desc: DataDescriptions) -> None:
    """Store the mapping from rigid-body IDs to names."""
    for rigid_body in desc.rigid_bodies:
        rigid_body_names[rigid_body.id_num] = rigid_body.name
        print(
            f"Discovered rigid body: "
            f"id={rigid_body.id_num}, name={rigid_body.name!r}"
        )


def receive_new_frame(data_frame: DataFrame) -> None:
    """Inspect incoming tracking frames."""
    global num_frames
    num_frames += 1

    # Printing every frame produces too much output.
    if num_frames % 100 != 0:
        return

    print(
        f"\nFrame {data_frame.prefix.frame_number}, "
        f"Motive timestamp={data_frame.suffix.timestamp:.6f}"
    )

    for rigid_body in data_frame.rigid_bodies:
        name = rigid_body_names.get(
            rigid_body.id_num,
            f"unknown-{rigid_body.id_num}",
        )

        x, y, z = rigid_body.pos
        qx, qy, qz, qw = rigid_body.rot

        print(
            f"  {name}: "
            f"id={rigid_body.id_num}, "
            f"position=({x:.4f}, {y:.4f}, {z:.4f}), "
            f"rotation=({qx:.4f}, {qy:.4f}, {qz:.4f}, {qw:.4f}), "
            f"valid={rigid_body.tracking_valid}, "
            f"error={rigid_body.marker_error:.6f}"
        )



num_frames = 0
if __name__ == "__main__":
    client = NatNetClient(server_ip_address=SERVER_IP, local_ip_address="127.0.0.1", use_multicast=False)
    client.on_data_description_received_event.handlers.append(receive_new_desc)
    client.on_data_frame_received_event.handlers.append(receive_new_frame)

    with client:
        client.protocol_version = PROTOCOL_VERSION
        print(f"NatNet 버전 {client.protocol_version}")
        client.request_modeldef()

        try:
            while True:
                client.update_sync()
                time.sleep(0.001)   # Prevent busy loop
        except KeyboardInterrupt:
            print("Exiting..")