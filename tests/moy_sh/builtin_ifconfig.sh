# the station as the kernel holds it: /.net says what the harness's is
ifconfig
ifconfig wlan0 | head -n 1
ifconfig eth0; echo bad=$?
ifconfig wlan0 up; echo bad=$?
echo off > /.net
ifconfig
echo alone > /.net
ifconfig
ls /.radio; echo none=$?
