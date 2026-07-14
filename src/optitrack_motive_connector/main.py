from natnet import NatNetClient

client = NatNetClient(
    server_ip_address="127.0.0.1",
    local_ip_address="127.0.0.1",
    use_multicast=False
)

with client:
    print("Connected!")
    client.request_modeldef()