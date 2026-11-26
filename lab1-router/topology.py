r"""
topology.py - Genera topology.json y sX-runtime.json (formato de p4lang/tutorials).

Topología (3 routers P4, 4 hosts en subredes distintas):

   h1 (10.0.1.1) --p1                                  p1-- h3 (10.0.3.3)
                    \                                /
                     s1 --p3 ---- p1-- s2 --p2 ---- p3-- s3
                    /                                \
   h2 (10.0.2.2) --p2                                  p2-- h4 (10.0.4.4)

Uso:  python3 topology.py
"""
import json


P4INFO = "build/router.p4.p4info.txtpb"
BMV2_JSON = "build/router.json"

# host -> (número de subred, switch, puerto del switch)
HOSTS = {
    "h1": (1, "s1", 1),
    "h2": (2, "s1", 2),
    "h3": (3, "s3", 1),
    "h4": (4, "s3", 2),
}

# enlaces switch-switch: (switchA, puertoA, switchB, puertoB)
SW_LINKS = [
    ("s1", 3, "s2", 1),
    ("s2", 2, "s3", 3),
]

# Para cada switch: subred -> puerto de salida 
ROUTES = {
    "s1": {1: 1, 2: 2, 3: 3, 4: 3},
    "s2": {1: 1, 2: 1, 3: 2, 4: 2},
    "s3": {1: 3, 2: 3, 3: 1, 4: 2},
}


def port_mac(sw, port):
    """MAC de la interfaz (switch, puerto)."""
    return "08:00:00:%02x:%02x:00" % (int(sw[1:]), port)


def host_mac(n):
    return "08:00:00:00:%02x:11" % n


# Mapa de vecinos: (switch, puerto) -> host o (switch, puerto) del otro lado
neigh = {}
for h, (n, sw, p) in HOSTS.items():
    neigh[(sw, p)] = ("host", n)
for a, pa, b, pb in SW_LINKS:
    neigh[(a, pa)] = ("sw", b, pb)
    neigh[(b, pb)] = ("sw", a, pa)


def build_topology():
    hosts = {}
    for h, (n, sw, p) in HOSTS.items():
        gw = "10.0.%d.254" % n
        hosts[h] = {
            "ip": "10.0.%d.%d/24" % (n, n),
            "mac": host_mac(n),
            "commands": [
                "route add default gw %s dev eth0" % gw,
                "arp -i eth0 -s %s %s" % (gw, port_mac(sw, p)),
            ],
        }
    switches = {s: {"runtime_json": "%s-runtime.json" % s} for s in ROUTES}
    links = []
    for h, (n, sw, p) in HOSTS.items():
        links.append([h, "%s-p%d" % (sw, p)])
    for a, pa, b, pb in SW_LINKS:
        links.append(["%s-p%d" % (a, pa), "%s-p%d" % (b, pb)])
    return {"hosts": hosts, "switches": switches, "links": links}


def build_runtime(sw):
    entries = [{
        "table": "MyIngress.ipv4_lpm",
        "default_action": True,
        "action_name": "MyIngress.drop",
        "action_params": {},
    }]
    for net, port in sorted(ROUTES[sw].items()):
        nb = neigh[(sw, port)]
        dst = host_mac(nb[1]) if nb[0] == "host" else port_mac(nb[1], nb[2])
        entries.append({
            "table": "MyIngress.ipv4_lpm",
            "match": {"hdr.ipv4.dstAddr": ["10.0.%d.0" % net, 24]},
            "action_name": "MyIngress.ipv4_forward",
            "action_params": {
                "srcMac": port_mac(sw, port),
                "dstMac": dst,
                "port": port,
            },
        })
    return {
        "target": "bmv2",
        "p4info": P4INFO,
        "bmv2_json": BMV2_JSON,
        "table_entries": entries,
    }


def main():
    with open("topology.json", "w") as f:
        json.dump(build_topology(), f, indent=2)
    for sw in ROUTES:
        with open("%s-runtime.json" % sw, "w") as f:
            json.dump(build_runtime(sw), f, indent=2)
    print("Generados: topology.json, " +
          ", ".join("%s-runtime.json" % s for s in ROUTES))


if __name__ == "__main__":
    main()