"""
topology.py - Genera topology.json y s1-runtime.json (formato de p4lang/tutorials).

Topología (1 switch P4, 4 hosts en subredes distintas):

   h1 (10.0.1.1) --p1
   h2 (10.0.2.2) --p2--  s1
   h3 (10.0.3.3) --p3
   h4 (10.0.4.4) --p4

Cada flujo (IP origen, IP destino) entre hosts recibe un índice en flow_table.
Uso:  python3 topology.py [--threshold BYTES]
"""
import argparse
import json

P4INFO = "build/counters.p4.p4info.txtpb"
BMV2_JSON = "build/counters.json"
NUM_HOSTS = 4


def port_mac(port):
    """MAC de la interfaz (s1, puerto)."""
    return "08:00:00:01:%02x:00" % port


def host_mac(n):
    return "08:00:00:00:%02x:11" % n


def build_topology():
    hosts = {}
    for n in range(1, NUM_HOSTS + 1):
        gw = "10.0.%d.254" % n
        hosts["h%d" % n] = {
            "ip": "10.0.%d.%d/24" % (n, n),
            "mac": host_mac(n),
            "commands": [
                "route add default gw %s dev eth0" % gw,
                "arp -i eth0 -s %s %s" % (gw, port_mac(n)),
            ],
        }
    links = [["h%d" % n, "s1-p%d" % n] for n in range(1, NUM_HOSTS + 1)]
    return {
        "hosts": hosts,
        "switches": {"s1": {"runtime_json": "s1-runtime.json"}},
        "links": links,
    }


def build_runtime(threshold):
    entries = [
        {
            "table": "MyIngress.ipv4_lpm",
            "default_action": True,
            "action_name": "MyIngress.drop",
            "action_params": {},
        },
        {
            "table": "MyIngress.cfg_threshold",
            "default_action": True,
            "action_name": "MyIngress.set_threshold",
            "action_params": {"threshold": threshold},
        },
    ]
    # Rutas LPM
    for n in range(1, NUM_HOSTS + 1):
        entries.append({
            "table": "MyIngress.ipv4_lpm",
            "match": {"hdr.ipv4.dstAddr": ["10.0.%d.0" % n, 24]},
            "action_name": "MyIngress.ipv4_forward",
            "action_params": {
                "srcMac": port_mac(n),
                "dstMac": host_mac(n),
                "port": n,
            },
        })
    # Un flujo por cada par ordenado (origen, destino), con índices desde 1
    idx = 1
    for s in range(1, NUM_HOSTS + 1):
        for d in range(1, NUM_HOSTS + 1):
            if s == d:
                continue
            entries.append({
                "table": "MyIngress.flow_table",
                "match": {
                    "hdr.ipv4.srcAddr": "10.0.%d.%d" % (s, s),
                    "hdr.ipv4.dstAddr": "10.0.%d.%d" % (d, d),
                },
                "action_name": "MyIngress.set_flow",
                "action_params": {"idx": idx},
            })
            idx += 1
    return {
        "target": "bmv2",
        "p4info": P4INFO,
        "bmv2_json": BMV2_JSON,
        "table_entries": entries,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=int, default=1000000,
                    help="umbral de flujo elefante en bytes (por defecto 1000000)")
    args = ap.parse_args()
    with open("topology.json", "w") as f:
        json.dump(build_topology(), f, indent=2)
    with open("s1-runtime.json", "w") as f:
        json.dump(build_runtime(args.threshold), f, indent=2)
    print("Generados: topology.json, s1-runtime.json (umbral elefante = %d bytes)"
          % args.threshold)


if __name__ == "__main__":
    main()
