#!/usr/bin/env python3
"""
controller.py - Lee periódicamente los contadores del switch P4 y los imprime
en consola con formato legible.
 
Lee
  - contadores directos por flujo (flow_table, IP origen + IP destino)
  - contador global por protocolo (TCP, UDP, ICMP, otros)
  - registers de tamaño de paquetes (último, máximo, histograma)
  - bandera de flujo elefante marcada por el plano de datos
 
Usa P4Runtime (gRPC). Si el BMv2 instalado no implementa alguna lectura
(error UNIMPLEMENTED), esa lectura se hace por Thrift con simple_switch_CLI.
 
Uso:  python3 controller.py [--interval 5] [--addr 127.0.0.1:50051]
"""
import argparse
import json
import re
import socket
import subprocess
import sys
import time
 
import grpc
from google.protobuf import text_format
from p4.config.v1 import p4info_pb2
from p4.v1 import p4runtime_pb2, p4runtime_pb2_grpc
 
PROTOS = ["TCP", "UDP", "ICMP", "Otros"]
BINS = ["<= 128 B", "129 - 512 B", "513 - 1024 B", "> 1024 B"]
MAX_FLOWS = 64
UNIMPL = grpc.StatusCode.UNIMPLEMENTED
 
notes = set()      # avisos que se imprimen una sola vez
thrift_port = 9090
 
 
def note(msg):
    if msg not in notes:
        notes.add(msg)
        print("[aviso] " + msg)
 
 
# ---------------------------------------------------------------- p4info
 
def load_p4info(path):
    p4info = p4info_pb2.P4Info()
    try:
        with open(path) as f:
            text_format.Merge(f.read(), p4info)
    except IOError:
        sys.exit("No se pudo abrir %s (¿ya ejecutó make build?)" % path)
    return p4info
 
 
def find(items, name):
    """Devuelve (id, nombre completo) de un objeto del p4info."""
    for it in items:
        if it.preamble.name.split(".")[-1] == name:
            return it.preamble.id, it.preamble.name
    sys.exit("No se encontró '%s' en el p4info" % name)
 
 
def load_threshold(path):
    try:
        with open(path) as f:
            data = json.load(f)
        for e in data["table_entries"]:
            if e["table"].endswith("cfg_threshold"):
                return int(e["action_params"]["threshold"])
    except (IOError, KeyError, ValueError):
        pass
    return None
 
 
# ---------------------------------------------------------------- Thrift (respaldo)
 
def thrift_cmd(cmd):
    out = subprocess.run(["simple_switch_CLI", "--thrift-port", str(thrift_port)],
                         input=cmd + "\n", capture_output=True, text=True,
                         timeout=10).stdout
    return out
 
 
def thrift_register(name, size):
    out = thrift_cmd("register_read %s" % name)
    m = re.search(re.escape(name) + r"=\s*([0-9,\s]+)", out)
    vals = [0] * size
    if m:
        nums = [int(x) for x in m.group(1).replace("\n", " ").split(",") if x.strip()]
        for i, v in enumerate(nums[:size]):
            vals[i] = v
    return vals
 
 
def thrift_counter(name, size):
    vals = []
    for i in range(size):
        out = thrift_cmd("counter_read %s %d" % (name, i))
        m = re.search(r"bytes=(\d+), packets=(\d+)", out)
        vals.append((int(m.group(2)), int(m.group(1))) if m else (0, 0))
    return vals
 
 
# ---------------------------------------------------------------- P4Runtime
 
def read(stub, dev, fill):
    req = p4runtime_pb2.ReadRequest()
    req.device_id = dev
    fill(req.entities.add())
    for resp in stub.Read(req):
        for ent in resp.entities:
            yield ent
 
 
def read_flows(stub, dev, table_id, with_counters=False):
    """Devuelve la lista de (idx, ip_origen, ip_destino, table_entry)."""
    flows = []
 
    def fill(e):
        e.table_entry.table_id = table_id
        if with_counters:
            e.table_entry.counter_data.SetInParent()
 
    for ent in read(stub, dev, fill):
        te = ent.table_entry
        if not te.match:
            continue            # entrada por defecto
        src = dst = "?"
        for m in te.match:
            if m.field_id == 1:
                src = socket.inet_ntoa(m.exact.value)
            elif m.field_id == 2:
                dst = socket.inet_ntoa(m.exact.value)
        idx = int.from_bytes(te.action.action.params[0].value, "big")
        flows.append((idx, src, dst, te))
    flows.sort(key=lambda f: f[0])
    return flows
 
 
def read_direct(stub, dev, te):
    def fill(e):
        e.direct_counter_entry.table_entry.table_id = te.table_id
        for m in te.match:
            e.direct_counter_entry.table_entry.match.add().CopyFrom(m)
 
    for ent in read(stub, dev, fill):
        d = ent.direct_counter_entry.data
        return d.packet_count, d.byte_count
    return 0, 0
 
 
def read_flow_counters(stub, dev, table_id):
    flows = read_flows(stub, dev, table_id)
    out = []
    try:
        for idx, src, dst, te in flows:
            pkts, byts = read_direct(stub, dev, te)
            out.append((idx, src, dst, pkts, byts))
        return out
    except grpc.RpcError as e:
        if e.code() != UNIMPL:
            raise
    note("DirectCounterEntry no implementado, se leen los contadores desde la tabla")
    out = []
    for idx, src, dst, te in read_flows(stub, dev, table_id, with_counters=True):
        out.append((idx, src, dst, te.counter_data.packet_count, te.counter_data.byte_count))
    return out
 
 
def read_register(stub, dev, rid, name, size):
    vals = [0] * size
    try:
        def fill(e):
            e.register_entry.register_id = rid
 
        for ent in read(stub, dev, fill):
            r = ent.register_entry
            i = r.index.index
            if 0 <= i < size:
                vals[i] = int.from_bytes(r.data.bitstring, "big")
        return vals
    except grpc.RpcError as e:
        if e.code() != UNIMPL:
            raise
    note("RegisterEntry no implementado en P4Runtime, se leen los registers por Thrift (puerto %d)"
         % thrift_port)
    return thrift_register(name, size)
 
 
def read_proto_counter(stub, dev, cid, name):
    vals = [(0, 0)] * len(PROTOS)
    try:
        def fill(e):
            e.counter_entry.counter_id = cid
 
        for ent in read(stub, dev, fill):
            c = ent.counter_entry
            i = c.index.index
            if 0 <= i < len(PROTOS):
                vals[i] = (c.data.packet_count, c.data.byte_count)
        return vals
    except grpc.RpcError as e:
        if e.code() != UNIMPL:
            raise
    note("CounterEntry no implementado en P4Runtime, se lee el contador por Thrift (puerto %d)"
         % thrift_port)
    return thrift_counter(name, len(PROTOS))
 
 
# ---------------------------------------------------------------- salida
 
def fmt_bytes(n):
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024.0)
    return "%.2f MB" % (n / (1024.0 * 1024.0))
 
 
def render(snap, prev, dt, threshold):
    print("=" * 84)
    print(" Estadísticas del switch s1   %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 84)
 
    print("\n Contadores globales por protocolo")
    print(" %-10s %12s %14s" % ("Protocolo", "Paquetes", "Bytes"))
    for name, (p, b) in zip(PROTOS, snap["protos"]):
        print(" %-10s %12d %14d" % (name, p, b))
 
    print("\n Histograma de tamaños de paquete (con cabecera Ethernet)")
    print(" %-14s %12s" % ("Rango", "Paquetes"))
    for name, n in zip(BINS, snap["hist"]):
        print(" %-14s %12d" % (name, n))
 
    umbral = fmt_bytes(threshold) if threshold else "desconocido"
    print("\n Flujos activos (umbral de flujo elefante: %s)" % umbral)
    print(" %-26s %9s %12s %10s %6s %6s  %s" %
          ("Flujo", "Paquetes", "Bytes", "kbps", "Máx", "Últ", "Estado"))
    activos = 0
    elefantes = []
    for idx, src, dst, pkts, byts in snap["flows"]:
        if pkts == 0:
            continue
        activos += 1
        old = prev.get(idx, 0)
        kbps = (byts - old) * 8.0 / 1000.0 / dt if dt > 0 else 0.0
        eleph = snap["elephant"][idx] == 1
        if eleph:
            elefantes.append("%s -> %s" % (src, dst))
        print(" %-26s %9d %12d %10.1f %6d %6d  %s" %
              ("%s -> %s" % (src, dst), pkts, byts, kbps,
               snap["max"][idx], snap["last"][idx],
               "ELEFANTE" if eleph else "normal"))
    if activos == 0:
        print(" (sin tráfico registrado)")
    print("\n Flujos configurados: %d, activos: %d, elefantes: %d" %
          (len(snap["flows"]), activos, len(elefantes)))
    for e in elefantes:
        print(" [ALERTA] flujo elefante detectado: %s" % e)
    print("")
    sys.stdout.flush()
 
 
# ---------------------------------------------------------------- main
 
def collect(stub, dev, ids, names):
    return {
        "flows": read_flow_counters(stub, dev, ids["flow_table"]),
        "protos": read_proto_counter(stub, dev, ids["proto_counter"], names["proto_counter"]),
        "hist": read_register(stub, dev, ids["size_hist"], names["size_hist"], len(BINS)),
        "max": read_register(stub, dev, ids["flow_max_size"], names["flow_max_size"], MAX_FLOWS),
        "last": read_register(stub, dev, ids["flow_last_size"], names["flow_last_size"], MAX_FLOWS),
        "elephant": read_register(stub, dev, ids["flow_elephant"], names["flow_elephant"], MAX_FLOWS),
    }
 
 
def main():
    global thrift_port
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--addr", default="127.0.0.1:50051", help="dirección gRPC del switch")
    ap.add_argument("--thrift-port", type=int, default=9090, help="puerto Thrift del switch")
    ap.add_argument("--device-id", type=int, default=0)
    ap.add_argument("--p4info", default="build/counters.p4.p4info.txtpb")
    ap.add_argument("--runtime", default="s1-runtime.json",
                    help="JSON de runtime (solo se usa para mostrar el umbral)")
    ap.add_argument("--interval", type=float, default=5.0, help="segundos entre lecturas")
    ap.add_argument("--once", action="store_true", help="leer una sola vez y salir")
    args = ap.parse_args()
    thrift_port = args.thrift_port
 
    p4info = load_p4info(args.p4info)
    ids, names = {}, {}
    for key, items in [("flow_table", p4info.tables),
                       ("proto_counter", p4info.counters),
                       ("size_hist", p4info.registers),
                       ("flow_max_size", p4info.registers),
                       ("flow_last_size", p4info.registers),
                       ("flow_elephant", p4info.registers)]:
        ids[key], names[key] = find(items, key)
    threshold = load_threshold(args.runtime)
 
    channel = grpc.insecure_channel(args.addr)
    stub = p4runtime_pb2_grpc.P4RuntimeStub(channel)
 
    prev, prev_time = {}, time.time()
    print("Leyendo %s cada %.0f s (Ctrl+C para salir)" % (args.addr, args.interval))
    try:
        while True:
            try:
                snap = collect(stub, args.device_id, ids, names)
            except grpc.RpcError as e:
                print("Error gRPC %s: %s" % (e.code(), e.details()))
                if args.once:
                    sys.exit(1)
                time.sleep(args.interval)
                continue
            now = time.time()
            render(snap, prev, now - prev_time, threshold)
            prev = {idx: byts for idx, _, _, _, byts in snap["flows"]}
            prev_time = now
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nSaliendo.")
 
 
if __name__ == "__main__":
    main()
 