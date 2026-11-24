printf 'Apple\nbanana\napple pie\n' > f
grep apple f
grep -i apple f
grep -v apple f
grep -n -c apple f
grep -q pear f; echo none=$?
grep; echo usage=$?
printf 'x\nan apple' > g
grep apple g
