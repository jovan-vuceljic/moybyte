# a name's address, through the station's DNS server
nslookup router.lan
nslookup 10.0.0.7
nslookup nowhere.lan; echo missing=$?
nslookup slow.lan | tail -n 1
nslookup; echo bad=$?
nslookup -x router.lan; echo bad=$?
cat /.radio
# a station that is down: held, it dials and the name is asked once it is up
echo off > /.net
nslookup router.lan | tail -n 1
cat /.radio
# held with nothing to dial
echo alone > /.net
nslookup router.lan; echo down=$?
cat /.radio
