# a file is read a chunk at a time, of any size, by every reader
i=0; while [ $i -lt 4096 ]; do echo "line $i 0123456789"; i=$((i+1)); done > big
wc -c big; wc -l < big; md5sum big; sha256sum big
cat big | md5sum
head -n 2 big
tail -n 2 big; tail -c 9 big; tail -n 1 < big
grep -c "line 7" big; grep "line 4095 " big; grep -n 'line 2048 ' < big
sort -r big | head -n 1
cut -c 1-9 big | tail -n 1
while read a b c; do last=$b; done < big; echo last=$last
# a script sourced reads in chunks too
i=0; while [ $i -lt 2000 ]; do echo "n=$i # padding to make the script long"; i=$((i+1)); done > s.sh
. ./s.sh; echo n=$n
# a descriptor kept open reads on from where it was, and seeks
exec 4< big; read x <&4; echo "$x"; head -n 1 <&4; exec 4<&-
# what was there at the open is what is read
exec 5< big; echo gone > big; head -n 1 <&5; exec 5<&-
cat nofile; echo nofile=$?
cat .; echo dir=$?
