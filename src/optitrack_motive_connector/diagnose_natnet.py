"""Diagnose model-definition compatibility with a Motive NatNet server.

Run on the Motive machine with:

    uv run python src/optitrack_motive_connector/diagnose_natnet.py

For a server on another machine:

    uv run python src/optitrack_motive_connector/diagnose_natnet.py \
        --server-ip 192.168.1.10 --local-ip 192.168.1.20
"""

from __future__ import annotations

import argparse
import time

from natnet import DataDescriptions, NatNetClient, Version


VERSIONS_TO_TEST = (
    Version(4, 3),
    Version(4, 2),
    Version(4, 1),
    Version(4, 0),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test which NatNet bitstream versions can decode Motive model definitions."
    )
    parser.add_argument(
        "--server-ip",
        default="127.0.0.1",
        help="Motive server IP address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--local-ip",
        default="127.0.0.1",
        help="This machine's IP address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Seconds to wait for each model definition (default: 3)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    received_descriptions = 0

    def on_description(_: DataDescriptions) -> None:
        nonlocal received_descriptions
        received_descriptions += 1

    client = NatNetClient(
        server_ip_address=args.server_ip,
        local_ip_address=args.local_ip,
        use_multicast=False,
    )
    client.on_data_description_received_event.handlers.append(on_description)

    print(f"Motive server: {args.server_ip}")
    print(f"Local address: {args.local_ip}")
    print("Connecting with unicast...")

    results: list[tuple[Version, str]] = []

    with client:
        server_version = client.server_info.server_version
        original_protocol = client.protocol_version
        print(f"Motive version reported by server: {server_version}")
        print(f"Negotiated NatNet protocol: {original_protocol}")
        print()

        try:
            for version in VERSIONS_TO_TEST:
                print(f"Testing NatNet {version}...", end=" ", flush=True)
                received_before = received_descriptions

                try:
                    client.protocol_version = version
                    client.request_modeldef()

                    deadline = time.monotonic() + args.timeout
                    while (
                        received_descriptions == received_before
                        and time.monotonic() < deadline
                    ):
                        client.update_sync()
                        time.sleep(0.02)

                    if received_descriptions > received_before:
                        result = "PASS"
                    else:
                        result = "TIMEOUT (no model definition received)"
                except UnicodeDecodeError as error:
                    result = f"FAIL ({error})"
                except Exception as error:  # Keep testing the remaining versions.
                    result = f"FAIL ({type(error).__name__}: {error})"

                results.append((version, result))
                print(result)
        finally:
            if original_protocol is not None:
                try:
                    client.protocol_version = original_protocol
                    print(f"\nRestored NatNet protocol to {original_protocol}.")
                except Exception as error:
                    print(f"\nWARNING: could not restore protocol: {error}")

    print("\nSummary")
    for version, result in results:
        print(f"  NatNet {version}: {result}")

    passing = [str(version) for version, result in results if result == "PASS"]
    if passing:
        print(f"\nWorking model-definition versions: {', '.join(passing)}")
    else:
        print("\nNo tested version decoded the model definition successfully.")
        print("If ASCII-only marker names work, the remaining issue is string encoding.")


if __name__ == "__main__":
    main()
