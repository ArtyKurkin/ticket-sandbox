"""Standalone stdlib-only checker. No Docker SDK, credentials, exec or shell."""
import hashlib
import http.client
import ipaddress
import json
import os
import socket
import sys

MAX_BODY = 1024


def probe(ipv4, challenge, *, timeout=2.0, connection_factory=http.client.HTTPConnection):
    address = ipaddress.IPv4Address(ipv4)
    if not any(address in ipaddress.IPv4Network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
        raise ValueError('endpoint_invalid')
    if len(challenge) != 64 or any(c not in '0123456789abcdef' for c in challenge):
        raise ValueError('challenge_invalid')
    # Fixed endpoint, numeric IPv4, no DNS, proxy, redirect or task-provided URL.
    conn = connection_factory(str(address), 8080, timeout=timeout)
    try:
        conn.request('GET', '/probe', headers={'X-PoC-Challenge':challenge, 'Connection':'close'})
        response = conn.getresponse()
        if 300 <= response.status < 400:
            return {'result':'failed', 'reason':'redirect_rejected', 'evidence':{'status':response.status}}
        raw = response.read(MAX_BODY+1)
        try:
            body = json.loads(raw) if len(raw) <= MAX_BODY else None
        except (ValueError, UnicodeError):
            body = None
        good = response.status == 200 and body == {'challenge':challenge, 'service':'synthetic-ipv4-v1'}
        return {'result':'passed' if good else 'failed', 'reason':'probe_passed' if good else 'unexpected_http_response',
                'evidence':{'status':response.status,'response_digest':hashlib.sha256(raw).hexdigest(),
                            'challenge_response_matched':good}}
    except ConnectionRefusedError:
        return {'result':'failed','reason':'service_unreachable','evidence':{}}
    except (TimeoutError, socket.timeout):
        return {'result':'unknown','reason':'probe_timeout','evidence':{}}
    except (OSError, http.client.HTTPException):
        return {'result':'unknown','reason':'probe_transport_error','evidence':{}}
    finally:
        conn.close()


def main():
    try:
        result = probe(os.environ['POC_TARGET_IPV4'], os.environ['POC_CHALLENGE'])
        print(json.dumps(result, sort_keys=True))
        return 0  # Verdict travels in validated protocol, not this exit code.
    except Exception:
        print(json.dumps({'result':'unknown','reason':'runner_configuration_invalid','evidence':{}}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
