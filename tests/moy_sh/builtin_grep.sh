printf 'Apple\nbanana\napple pie\n' > f
grep apple f
grep -i apple f
grep -v apple f
grep -n -c apple f
grep -q pear f; echo none=$?
grep; echo usage=$?
printf 'x\nan apple' > g
grep apple g
l=; i=0; while [ $i -lt 300 ]; do l="${l}0123456789"; i=$((i+1)); done
printf '%sneedle\nshort needle\n' "$l" > /long.txt
grep -c needle /long.txt
grep needle /long.txt | wc -c
