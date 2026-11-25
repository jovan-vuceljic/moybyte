printf 'hello world\n' | tr a-z A-Z
printf 'hello world\n' | tr -d lo
printf 'aabbccdd\n' | tr abcd xy
printf 'a  b   c\n' | tr -s ' '
printf 'aaxxbb\n' | tr -s a-z A-Z
printf 'a\tb\n' | tr '\t' ,
printf 'Mixed Case 42\n' | tr '[:upper:]' '[:lower:]'
printf 'a1 b2\tc3\n' | tr -d '[:digit:][:space:]'; echo
printf 'a-b\n' | tr 'a-' 'XY'
printf 'abc' | tr abc '\101-\103'; echo
printf '' | tr a b; echo empty=$?
tr a; echo usage=$?
tr -d a b; echo usage=$?
tr z-a x; echo backwards=$?
tr a ''; echo empty-set2=$?
tr -z a b; echo bad=$?
