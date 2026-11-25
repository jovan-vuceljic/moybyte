# a pipe holds its writer's whole stream, a chunk of the heap at a time
i=0; while [ $i -lt 4096 ]; do echo 0123456789abcde; i=$((i+1)); done | tee t64 | wc -c
md5sum t64; cat t64 | md5sum; cat t64 | cat | cat | wc -l
# a stream past what a pipe holds is said once, its writer ended, and the
# reader reads what came before it
l=y; while [ ${#l} -lt 1023 ]; do l=$l$l; done; l=${l%?}
yes() { while :; do echo $l; done; }
yes | head -n 1 | wc -c; echo status=$?
yes 2>&1 | wc -c
yes 2>/dev/null | wc -l
{ yes; echo never; } | grep -c never
echo after
