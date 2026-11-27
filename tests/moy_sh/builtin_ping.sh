# ICMP echoes, in iputils' lines; the harness's 10.0.0.1 answers each
ping -c 2 -i 0.2 router.lan
echo answered=$?
ping -c 4 -i 0.2 lossy.lan; echo some=$?
ping -c 2 -i 0.2 -W 0.3 10.0.0.9; echo none=$?
ping -c 1 nowhere.lan; echo missing=$?
ping -c 0 router.lan; echo bad=$?
ping -c two router.lan; echo bad=$?
ping -i 0.1 router.lan; echo bad=$?
ping -x router.lan; echo bad=$?
ping; echo bad=$?
ping router.lan lossy.lan; echo bad=$?
ping -c 1 router.lan | wc -l
cat /.radio
echo alone > /.net
ping -c 1 router.lan; echo down=$?
cat /.radio
