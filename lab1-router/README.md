# Lab 1 - Router IPv4 estático

Tres routers P4 (v1model, BMv2) en línea, `s1 - s2 - s3`, con cuatro hosts en subredes distintas.

```
h1 10.0.1.1 -- p1                                  p1 -- h3 10.0.3.3
                 \                                /
                  s1 --p3 ---- p1-- s2 --p2 ---- p3-- s3
                 /                                \
h2 10.0.2.2 -- p2                                  p2 -- h4 10.0.4.4
```

## Contenido

| Archivo | Descripción |
|---|---|
| `router.p4` | Parser (Ethernet, IPv4), tabla LPM `ipv4_lpm`, TTL, reescritura de MAC, default drop |
| `topology.py` | Genera `topology.json` y `s1/s2/s3-runtime.json` (rutas estáticas) |
| `topology.json`, `s*.json` | Salida ya generada de `topology.py` |
| `test_ttl.py` | Scapy: `send` envía ICMP con un TTL dado, `recv` imprime el TTL recibido |
| `demo.cmd` | Escenario de pruebas para el CLI de Mininet |
| `Makefile` | Compila, genera la topología y lanza Mininet |

## Requisitos

`p4c-bm2-ss`, `simple_switch_grpc`, Mininet, Scapy y el repositorio `p4lang/tutorials`
(se usa su `utils/run_exercise.py`). Si no está en `~/tutorials`: `make run TUTORIALS=/ruta/tutorials`.

## Ejecución

```
make run          # compila, genera la topología y abre Mininet
mininet> source demo.cmd
make clean
```

## Qué demuestra cada prueba

| Requisito | Prueba | Resultado esperado |
|---|---|---|
| Conectividad entre hosts | `pingall` | 0% de pérdida |
| TTL decrementa por hop | `test_ttl.py send ... --ttl 64` | h3 recibe TTL=61 (3 routers) |
| Descarte con TTL agotado | `--ttl 3` | no llega nada a h3; `--ttl 4` sí llega, con TTL=1 |
| Reescritura de MAC | `tcpdump -e -i h3-eth0` en h3 | MAC origen `08:00:00:03:01:00` (interfaz de s3), no la de h1 |
| Sin ruta, default drop | `ping 10.0.9.9` desde h1 | 100% de pérdida |

Para capturar con Wireshark, los `.pcap` quedan en `pcaps/` (cada puerto de cada switch).

## Notas de diseño

- Las rutas se cargan desde el control plane (`sX-runtime.json`), no están en el P4.
- Paquetes no IPv4 (ARP, etc.) se descartan; los hosts usan entradas ARP estáticas hacia su gateway.
- Si `ttl <= 1` se descarta antes de consultar la tabla.
- No implementado (opcional): ICMP Time Exceeded e IPv6.
