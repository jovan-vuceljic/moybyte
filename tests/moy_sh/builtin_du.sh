mkdir -p d/a/b d/c
printf 'x' > d/one
i=0; while [ $i -lt 103 ]; do printf '0123456789'; i=$((i+1)); done > d/a/k
cp d/a/k d/a/b/k2
du d
du -s d
du -h d
du -sh d/a
du d/one
printf '0123456789abcdef' > big; for i in 1 2 3 4 5 6 7 8 9 10; do cat big big > t; cat t > big; done
du -h big; echo >> big; du -h big
for i in 1 2 3 4 5 6; do cat big big > t; cat t > big; done
du -h big; du big
du nosuch; echo missing=$?
du -z; echo bad=$?
