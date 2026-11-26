"""
ttl_test.py - Pruebas del router P4 con Scapy.
"""
import argparse
import sys
from scapy.all import IP, ICMP, Raw, send, sniff, get_if_list


def get_iface():
    for i in get_if_list():
        if "eth0" in i:
            return i
    sys.exit("No se encontró la interfaz eth0")


def handle(pkt):
    if IP in pkt and ICMP in pkt and pkt[ICMP].type == 8:
        print("[recv] %s -> %s  TTL=%d" % (pkt[IP].src, pkt[IP].dst, pkt[IP].ttl))
        sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["send", "recv"])
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--ttl", type=int, default=64)
    ap.add_argument("--count", type=int, default=3)
    args = ap.parse_args()

    if args.mode == "recv":
        iface = get_iface()
        print("Escuchando en %s (Ctrl+C para salir)" % iface)
        sniff(iface=iface, prn=handle)
    else:
        if not args.dst:
            sys.exit("Falta la IP destino")
        for i in range(args.count):
            print("[send] -> %s  TTL=%d  (paquete %d)" % (args.dst, args.ttl, i + 1))
            send(IP(dst=args.dst, ttl=args.ttl) / ICMP() / Raw(b"p4-test"), verbose=False)


if __name__ == "__main__":
    main()