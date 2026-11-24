h1 sh quiet_host.sh
h2 sh quiet_host.sh
h3 sh quiet_host.sh
h4 sh quiet_host.sh
h1 python3 gen_traffic.py 10.0.2.2 --proto udp --count 100 --size 100
h1 python3 gen_traffic.py 10.0.3.3 --proto tcp --count 50 --size 20
h2 python3 gen_traffic.py 10.0.4.4 --proto other --count 20 --size 200
h3 ping -c 5 10.0.1.1
