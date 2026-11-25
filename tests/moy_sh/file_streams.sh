# a file written goes to the store a chunk at a time, of any size
i=0; while [ $i -lt 4096 ]; do echo 0123456789abcde; i=$((i+1)); done > big
wc -c big; md5sum big
cat big | tee copy | wc -c
md5sum copy; tail -n 1 copy
echo end >> copy; tee -a copy < big > /dev/null; wc -c copy
# written over, it is whole until its last close: its old bytes read back
cat big > big; wc -c big
exec 3> copy; echo new >&3; wc -c copy; exec 3>&-; cat copy
ls -a
echo x > nodir/f; echo nodir=$?
