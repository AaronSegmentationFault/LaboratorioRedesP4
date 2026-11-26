# Escenario de prueba del Lab 1. En el CLI de Mininet:  mininet> source demo.cmd

# 1. Conectividad entre los 4 hosts
pingall

# 2. TTL: h3 escucha; h1 envía con TTL 64 (debe llegar con 61, pasa por s1, s2 y s3)
h3 python3 test_ttl.py recv > /tmp/h3_recv.txt 2>&1 &
sh sleep 2
h1 python3 test_ttl.py send 10.0.3.3 --ttl 64 --count 3
sh sleep 2
sh cat /tmp/h3_recv.txt

# 3. TTL justo suficiente (4 -> llega con 1) y TTL agotado (3 -> se descarta en s3)
h1 python3 test_ttl.py send 10.0.3.3 --ttl 4 --count 2
h1 python3 test_ttl.py send 10.0.3.3 --ttl 3 --count 2
sh sleep 2
sh cat /tmp/h3_recv.txt

# 4. Sin ruta: 10.0.9.9 no está en ninguna tabla, s1 aplica default drop
h1 ping -c 3 -W 1 10.0.9.9
