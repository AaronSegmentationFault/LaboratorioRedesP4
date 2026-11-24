/* counters.p4 - Contadores y estadísticas de tráfico (v1model, target BMv2)
 *
 * Funciones:
 *   - Reenvío IPv4 por LPM (mismo esquema del Lab 1), con TTL y reescritura de MAC
 *   - Contadores directos por flujo (IP origen + IP destino) en la tabla flow_table
 *   - Contadores globales por protocolo: TCP, UDP, ICMP y otros
 *   - Registers con el tamaño de los paquetes (último, máximo, bytes acumulados
 *     por flujo e histograma global de tamaños)
 *   - Detección de flujo elefante, con umbral configurable desde el control plane
 *
 * Todos los tamaños usan standard_metadata.packet_length, que incluye la
 * cabecera Ethernet (14 bytes) y no incluye el FCS.
 */
#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4  = 0x0800;
const bit<8>  PROTO_ICMP = 1;
const bit<8>  PROTO_TCP  = 6;
const bit<8>  PROTO_UDP  = 17;

// Índices del contador global por protocolo
const bit<32> IDX_TCP   = 0;
const bit<32> IDX_UDP   = 1;
const bit<32> IDX_ICMP  = 2;
const bit<32> IDX_OTROS = 3;
const bit<32> NUM_PROTOS = 4;

// Máximo de flujos registrados (el índice 0 se reserva para "sin flujo")
const bit<32> MAX_FLOWS = 64;
// Cantidad de rangos del histograma de tamaños
const bit<32> NUM_BINS = 4;

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

/*************************** HEADERS ***************************/

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

struct metadata {
    bit<16> flow_id;     // índice del flujo (0 = sin flujo registrado)
    bit<64> threshold;   // umbral de flujo elefante en bytes
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
}

/**************************** PARSER ****************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_IPV4: parse_ipv4;
            default:   accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition accept;
    }
}

/************************ VERIFY CHECKSUM ************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply {
        verify_checksum(
            hdr.ipv4.isValid() && hdr.ipv4.ihl == 5,
            { hdr.ipv4.version, hdr.ipv4.ihl, hdr.ipv4.diffserv,
              hdr.ipv4.totalLen, hdr.ipv4.identification,
              hdr.ipv4.flags, hdr.ipv4.fragOffset, hdr.ipv4.ttl,
              hdr.ipv4.protocol, hdr.ipv4.srcAddr, hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}

/************************** INGRESS ****************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    // Contador global por protocolo (paquetes y bytes)
    counter(NUM_PROTOS, CounterType.packets_and_bytes) proto_counter;

    // Contador directo asociado a la tabla flow_table (un contador por flujo)
    direct_counter(CounterType.packets_and_bytes) flow_counter;

    // Registers con el tamaño de los paquetes, indexados por flow_id
    register<bit<64>>(MAX_FLOWS) flow_bytes;       // bytes acumulados
    register<bit<32>>(MAX_FLOWS) flow_max_size;    // paquete más grande visto
    register<bit<32>>(MAX_FLOWS) flow_last_size;   // último paquete visto
    register<bit<1>>(MAX_FLOWS)  flow_elephant;    // 1 = flujo elefante
    // Histograma global de tamaños (paquetes por rango)
    register<bit<64>>(NUM_BINS)  size_hist;

    action drop() {
        mark_to_drop(standard_metadata);
    }

    // srcMac: MAC de la interfaz de salida del router
    // dstMac: MAC del siguiente salto
    action ipv4_forward(macAddr_t srcMac, macAddr_t dstMac, egressSpec_t port) {
        standard_metadata.egress_spec = port;
        hdr.ethernet.srcAddr = srcMac;
        hdr.ethernet.dstAddr = dstMac;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }

    table ipv4_lpm {
        key = {
            hdr.ipv4.dstAddr: lpm;
        }
        actions = {
            ipv4_forward;
            drop;
        }
        size = 1024;
        default_action = drop();
    }

    // Asigna un índice a cada flujo (IP origen + IP destino) definido por el control plane
    action set_flow(bit<16> idx) {
        meta.flow_id = idx;
    }

    action no_flow() {
        meta.flow_id = 0;
    }

    table flow_table {
        key = {
            hdr.ipv4.srcAddr: exact;
            hdr.ipv4.dstAddr: exact;
        }
        actions = {
            set_flow;
            no_flow;
        }
        counters = flow_counter;
        size = 64;
        default_action = no_flow();
    }

    // Umbral de flujo elefante en bytes. Se cambia modificando la acción por defecto
    action set_threshold(bit<64> threshold) {
        meta.threshold = threshold;
    }

    table cfg_threshold {
        actions = {
            set_threshold;
        }
        size = 1;
        default_action = set_threshold(1000000);
    }

    apply {
        bit<32> idx      = 0;
        bit<32> pkt_len  = standard_metadata.packet_length;
        bit<32> proto_ix = IDX_OTROS;
        bit<32> bin_ix   = 3;
        bit<64> acc      = 0;
        bit<64> hist     = 0;
        bit<32> max_sz   = 0;

        if (hdr.ipv4.isValid()) {
            cfg_threshold.apply();

            // 1. Contador global por protocolo
            if (hdr.ipv4.protocol == PROTO_TCP) {
                proto_ix = IDX_TCP;
            } else if (hdr.ipv4.protocol == PROTO_UDP) {
                proto_ix = IDX_UDP;
            } else if (hdr.ipv4.protocol == PROTO_ICMP) {
                proto_ix = IDX_ICMP;
            }
            proto_counter.count(proto_ix);

            // 2. Histograma global de tamaños
            if (pkt_len <= 128) {
                bin_ix = 0;
            } else if (pkt_len <= 512) {
                bin_ix = 1;
            } else if (pkt_len <= 1024) {
                bin_ix = 2;
            }
            size_hist.read(hist, bin_ix);
            size_hist.write(bin_ix, hist + 1);

            // 3. Contador directo por flujo y registers por flujo
            if (flow_table.apply().hit) {
                idx = (bit<32>) meta.flow_id;

                flow_bytes.read(acc, idx);
                acc = acc + (bit<64>) pkt_len;
                flow_bytes.write(idx, acc);

                flow_last_size.write(idx, pkt_len);
                flow_max_size.read(max_sz, idx);
                if (pkt_len > max_sz) {
                    flow_max_size.write(idx, pkt_len);
                }

                // 4. Flujo elefante: bytes acumulados sobre el umbral
                if (acc > meta.threshold) {
                    flow_elephant.write(idx, 1);
                }
            }

            // Reenvío
            if (hdr.ipv4.ttl <= 1) {
                drop();
            } else {
                ipv4_lpm.apply();
            }
        } else {
            drop();
        }
    }
}

/************************** EGRESS *****************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply { }
}

/*********************** COMPUTE CHECKSUM ***********************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {
        update_checksum(
            hdr.ipv4.isValid() && hdr.ipv4.ihl == 5,
            { hdr.ipv4.version, hdr.ipv4.ihl, hdr.ipv4.diffserv,
              hdr.ipv4.totalLen, hdr.ipv4.identification,
              hdr.ipv4.flags, hdr.ipv4.fragOffset, hdr.ipv4.ttl,
              hdr.ipv4.protocol, hdr.ipv4.srcAddr, hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}

/************************** DEPARSER ***************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
    }
}

/*************************** SWITCH ****************************/

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
