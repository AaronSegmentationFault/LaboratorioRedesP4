# Laboratorio Redes Programables con P4

Curso de Redes de Computadoras, Universidad de Costa Rica. Grupo de 2 estudiantes.

| Carpeta | Contenido |
|---|---|
| `lab1-router/` | Router IPv4 estático (3 routers P4, 4 hosts) |
| `lab2-counters/` | Contadores y estadísticas de tráfico, detección de flujo elefante |
| `informe/` | Informe de investigación (PDF) |

## Requisitos (todos los labs)

- `p4c-bm2-ss` y `simple_switch_grpc` (BMv2), Mininet, Scapy, iperf
- Paquete Python `p4runtime`
- `p4lang/tutorials` clonado en `~/tutorials` (o pasar `TUTORIALS=/ruta` a `make`)

## Cómo ejecutar

Cada laboratorio se corre desde su carpeta; las instrucciones y los resultados esperados
están en su propio README.

```
cd lab1-router   && make run     # luego, en Mininet: source demo.cmd
cd lab2-counters && make run     # terminal 2: make controller
```

Limpiar con `make clean` en cada carpeta.

## Video demostrativo

Enlace: _(pegar aquí el enlace o agregar `demo.mp4`)_
