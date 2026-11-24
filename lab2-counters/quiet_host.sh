#!/bin/sh
# Evita que el kernel del host responda (ICMP inalcanzable, TCP RST) al tráfico
# generado con Scapy, para que los contadores solo reflejen lo inyectado.
iptables -A OUTPUT -p icmp --icmp-type destination-unreachable -j DROP
iptables -A OUTPUT -p tcp --tcp-flags RST RST -j DROP
