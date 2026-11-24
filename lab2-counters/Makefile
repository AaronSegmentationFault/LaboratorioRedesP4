# Makefile del Lab 2 (contadores y estadísticas de tráfico)
# Requiere p4c-bm2-ss, simple_switch_grpc y el repositorio p4lang/tutorials
# (se usa solo su script utils/run_exercise.py).

TUTORIALS ?= $(HOME)/tutorials
P4_SRC    = counters.p4
BUILD     = build
P4_JSON   = $(BUILD)/counters.json
P4_INFO   = $(BUILD)/counters.p4.p4info.txtpb
THRESHOLD ?= 1000000

.PHONY: all build topology run controller clean

all: run

build: $(P4_JSON)

$(P4_JSON): $(P4_SRC)
	mkdir -p $(BUILD) pcaps logs
	p4c-bm2-ss --p4v 16 --p4runtime-files $(P4_INFO) -o $(P4_JSON) $(P4_SRC)

topology:
	python3 topology.py --threshold $(THRESHOLD)

run: build topology
	sudo python3 $(TUTORIALS)/utils/run_exercise.py -t topology.json -j $(P4_JSON) -b simple_switch_grpc

controller:
	python3 controller.py --interval 5

clean:
	rm -rf $(BUILD) pcaps logs
