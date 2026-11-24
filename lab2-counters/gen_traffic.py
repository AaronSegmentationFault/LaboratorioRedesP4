#!/usr/bin/env python3
"""
gen_traffic.py - Genera tráfico controlado con Scapy desde un host de Mininet.
 
Ejemplos (dentro del CLI de Mininet)
  h1 python3 gen_traffic.py 10.0.2.2 --proto udp --count 100 --size 100
  h1 python3 gen_traffic.py 10.0.3.3 --proto tcp --count 50 --size 20
  h2 python3 gen_traffic.py 10.0.4.4 --proto other --count 20 --size 200
 
Imprime cuántos bytes debería contar el switch (incluye Ethernet, 14 bytes),
para compararlos con la salida del controlador.
"""
import argparse
import subprocess
import sys
 
from scapy.all import Ether, IP, ICMP, TCP, UDP, Raw, sendp
 
ETH_HDR = 14
BROADCAST = "ff:ff:ff:ff:ff:ff"
 
 
def gateway_mac():
    """MAC del gateway por defecto, leída de la tabla ARP estática del host."""
    try:
        route = subprocess.check_output(["ip", "route", "show", "default"]).decode()
        gw = route.split("via")[1].split()[0]
        with open("/proc/net/arp") as f:
            for line in f.readlines()[1:]:
                cols = line.split()
                if cols[0] == gw and cols[3] != "00:00:00:00:00:00":
                    return cols[3]
    except Exception:
        pass
    return BROADCAST
 
 
def build(args):
    if args.proto == "tcp":
        pkt = IP(dst=args.dst) / TCP(sport=args.sport, dport=args.dport, flags="S")
    elif args.proto == "udp":
        pkt = IP(dst=args.dst) / UDP(sport=args.sport, dport=args.dport)
    elif args.proto == "icmp":
        pkt = IP(dst=args.dst) / ICMP()
    else:
        pkt = IP(dst=args.dst, proto=253)   # protocolo reservado para experimentación
    return pkt / Raw(b"x" * args.size) if args.size > 0 else pkt
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dst", help="IP destino")
    ap.add_argument("--proto", choices=["tcp", "udp", "icmp", "other"], default="udp")
    ap.add_argument("--count", type=int, default=10, help="cantidad de paquetes")
    ap.add_argument("--size", type=int, default=100, help="bytes de carga útil")
    ap.add_argument("--interval", type=float, default=0.01, help="segundos entre paquetes")
    ap.add_argument("--sport", type=int, default=40000)
    ap.add_argument("--dport", type=int, default=9000)
    ap.add_argument("--iface", default="eth0")
    args = ap.parse_args()
 
    if args.size < 0 or args.count <= 0:
        sys.exit("size debe ser >= 0 y count > 0")
 
    frame = Ether(dst=gateway_mac()) / build(args)
    print("[send] %d paquetes %s -> %s, %d bytes por trama" %
          (args.count, args.proto.upper(), args.dst, len(frame)))
    sendp(frame, iface=args.iface, count=args.count, inter=args.interval, verbose=False)
    print("[done] esperado en el switch: %d paquetes, %d bytes" %
          (args.count, args.count * len(frame)))
 
 
if __name__ == "__main__":
    main()
 