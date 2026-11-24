# Lab 2 - Contadores y estadísticas de tráfico

Switch P4 (v1model, BMv2) que enruta IPv4 y mide el tráfico en el plano de datos.
Un controlador Python lee los contadores por P4Runtime cada 5 segundos.

## Contenido

| Archivo | Descripción |
|---|---|
| `counters.p4` | Programa P4 con contadores, registers y detección de flujo elefante |
| `topology.py` | Genera `topology.json` y `s1-runtime.json` (rutas, flujos y umbral) |
| `topology.json`, `s1-runtime.json` | Salida ya generada de `topology.py` |
| `controller.py` | Lector periódico de contadores (P4Runtime sobre gRPC) |
| `gen_traffic.py` | Generador de tráfico con Scapy (TCP, UDP, ICMP y otros) |
| `quiet_host.sh` | Silencia respuestas automáticas del kernel en los hosts |
| `demo.cmd` | Escenario de prueba para el CLI de Mininet |
| `Makefile` | Compila, genera la topología y lanza Mininet |

## Topología

Un switch `s1` y cuatro hosts, cada uno en su subred (mismo esquema del Lab 1).

```
h1 10.0.1.1 -- p1
h2 10.0.2.2 -- p2 -- s1
h3 10.0.3.3 -- p3
h4 10.0.4.4 -- p4
```

## Requisitos

- `p4c-bm2-ss`, `simple_switch_grpc`, Mininet, Scapy e iperf
- Paquete Python `p4runtime` (módulos `p4.v1` y `p4.config.v1`)
- Repositorio `p4lang/tutorials` clonado. Se usa su `utils/run_exercise.py`.
  Si no está en `~/tutorials`, pasar `TUTORIALS=/ruta/tutorials` a `make`.

## Ejecución

Terminal 1, compila y abre Mininet.

```
make run
```

Terminal 2, lanza el controlador (lee cada 5 s).

```
make controller
```

Para cambiar el umbral de flujo elefante (bytes) antes de lanzar.

```
make run THRESHOLD=500000
```

Para limpiar, `make clean`.

## Pruebas

### Escenario automático

En el CLI de Mininet.

```
mininet> source demo.cmd
```

Valores esperados en el controlador, contando desde cero.

| Flujo | Paquetes | Bytes |
|---|---|---|
| 10.0.1.1 -> 10.0.2.2 (UDP, carga 100 B) | 100 | 14200 |
| 10.0.1.1 -> 10.0.3.3 (TCP SYN, carga 20 B) | 50 | 3700 |
| 10.0.2.2 -> 10.0.4.4 (protocolo 253, carga 200 B) | 20 | 4680 |
| 10.0.3.3 -> 10.0.1.1 (ping, 5 solicitudes) | 5 | 490 |
| 10.0.1.1 -> 10.0.3.3 (ping, 5 respuestas) | 5 | 490 |

Hay que tener en cuenta lo siguiente.

- Los bytes incluyen la cabecera Ethernet (14 B). `gen_traffic.py` imprime los bytes esperados.
- El flujo 10.0.1.1 -> 10.0.3.3 suma TCP y ping. Se ve como 55 paquetes y 4190 bytes.
- Los globales por protocolo salen de sumar lo anterior. UDP 100 paquetes, TCP 50, ICMP 10 y Otros 20.
- `quiet_host.sh` evita que el kernel agregue respuestas (RST, ICMP inalcanzable) que alterarían los conteos.
- Si una trama sale menor a 60 B, comparar con Wireshark por posible relleno de Ethernet.

### Flujo elefante con iperf

```
mininet> h4 iperf -s -u > /dev/null &
mininet> h3 iperf -c 10.0.4.4 -u -b 8M -t 6
```

Con el umbral por defecto (1 000 000 B) el flujo 10.0.3.3 -> 10.0.4.4 queda marcado como
`ELEFANTE` y el controlador imprime la alerta. Los demás flujos siguen como `normal`.

### Verificación contra el tráfico inyectado

1. Ejecutar un comando de `gen_traffic.py` y anotar `esperado en el switch`.
2. Esperar a la siguiente lectura del controlador.
3. Comparar paquetes y bytes del flujo. Deben coincidir exactamente.

## Cómo cumple cada requisito

| Requisito | Dónde |
|---|---|
| Contadores directos por IP origen + destino | `flow_counter` asociado a `flow_table` |
| Contadores globales TCP, UDP, ICMP y otros | `proto_counter` (4 posiciones) |
| Tamaño de paquetes con registers | `flow_last_size`, `flow_max_size`, `flow_bytes` y `size_hist` |
| Script de lectura periódica | `controller.py`, formato de tabla en consola |
| Flujo elefante con umbral configurable | `flow_elephant` y tabla `cfg_threshold`, umbral en `topology.py --threshold` |
| Al menos 1 switch y 4 hosts con tráfico mixto | `topology.json`, `gen_traffic.py` e iperf |

## Notas de diseño

- Cada par ordenado de hosts tiene una entrada en `flow_table`. El índice del flujo
  (`set_flow`) sirve para direccionar los registers.
- El umbral vive en la acción por defecto de `cfg_threshold`. Se cambia regenerando
  `s1-runtime.json` con `topology.py --threshold`.
- Un flujo se marca elefante cuando sus bytes acumulados superan el umbral.
  La marca queda hasta reiniciar el switch.
- Se cuenta todo paquete IPv4 que entra, incluso si luego se descarta por TTL.
