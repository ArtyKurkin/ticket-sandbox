"""Run inside the E2E driver to test the actual ttyd/broker boundary."""
import json
import os
import urllib.request
import urllib.error

import docker

PROBE = r'''
import json,os,shutil,socket,struct
assert not os.path.exists('/var/run/docker.sock')
assert shutil.which('docker') is None
credential=json.load(open('/run/terminal/client.json'))['credential']
for changes in ({'credential':'wrong'}, {'container_id':'f'*64}, {'command':['id']}, {'exec_id':'f'*64}):
    obj={'version':2,'credential':credential,**changes}
    payload=json.dumps(obj).encode()
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(4)
        conn.connect('/run/terminal/broker.sock')
        conn.sendall(struct.pack('!cI',b'H',len(payload))+payload)
        try: accepted=conn.recv(1)==b'\x01'
        except ConnectionResetError: accepted=False
        assert not accepted, 'Broker accepted a forbidden request'
print('isolation-probe-passed')
'''


def main():
    client = docker.from_env()
    prefix = os.environ.get("TB_E2E_PREFIX", "tc-tb2-20261028-")
    results = []
    for mode in ("host_port", "docker_network"):
        terminal = client.containers.get(prefix + mode + "-terminal")
        assert all(mount["Destination"] != "/var/run/docker.sock" for mount in terminal.attrs["Mounts"])
        assert not any("docker.sock" in mount.get("Source", "") for mount in terminal.attrs["Mounts"])
        code, output = terminal.exec_run(["python3", "-I", "-c", PROBE])
        if code != 0:
            raise RuntimeError(mode + " isolation probe failed: " + output.decode(errors="replace"))
        if mode == "docker_network":
            attempt = terminal.labels["ticket-sandbox.attempt"]
            try:
                urllib.request.urlopen(f"http://{terminal.name}:7681/terminal/{attempt}/", timeout=3)
            except urllib.error.HTTPError as exc:
                assert exc.code == 401, "Direct ttyd did not require its gateway credential"
            else:
                raise RuntimeError("Direct ttyd bypassed Django gateway authentication")
        results.append({"mode": mode, "socketMounted": False, "dockerCLI": False,
                        "wrongCredentialDenied": True, "containerCommandAndExecSelectionDenied": True,
                        "directNetworkBypassDenied": True if mode == "docker_network" else "loopback-only"})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
