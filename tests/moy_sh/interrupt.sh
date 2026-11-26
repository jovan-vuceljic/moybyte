# Ctrl-C stops the running command and the rest of its line
touch /.interrupt; sleep 5; echo not-after
echo slept=$?
touch /.interrupt; while true; do :; done
echo loop=$?
trap 'echo caught' INT
touch /.interrupt; sleep 5
echo trapped=$?
# ping's summary is said at Ctrl-C too, and the radio's hold goes with it
echo 30 > /.interrupt; ping router.lan
echo pinged=$?
cat /.radio
