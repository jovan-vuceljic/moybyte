printf 'pear\napple\nBanana\napple\n' > f
sort f
sort -r f
sort -u f
printf 'abc\n0\n-1\n10\n9\n 2x\n2\n1.5\n-0\n.5\n' | sort -n
printf '1 b\n1 a\n2\n1 c\n' | sort -nu
printf '1 a\n1 b\n' | sort -rnu
printf '1 a\n1 b\n' | sort -rn
printf 'b\na' | sort
printf 'x\n' > g; sort f g
printf '' | sort; echo empty=$?
sort nosuch f; echo missing=$?
sort -z f; echo bad=$?
printf '0123456789abcdef' > l; for i in 1 2 3 4 5 6 7 8 9; do cat l l > t; cat t > l; done
printf '\nb\na\n' >> l; sort l | head -n 1 | wc -c
printf '0123456789abcdef\n' > big; for i in 1 2 3 4 5 6 7 8 9 10; do cat big big > t; cat t > big; done
sort big | wc -l; sort -u big
for i in 1 2 3 4; do cat big big > t; cat t > big; done
sort big; echo oom=$?
