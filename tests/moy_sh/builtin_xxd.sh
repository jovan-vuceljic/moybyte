printf 'hello\n' | xxd
printf '0123456789abcdefXYZ\000\377\177' > b
xxd b
xxd - < b | wc -l
printf '' | xxd; echo empty=$?
xxd nosuch; echo missing=$?
xxd b b; echo usage=$?
xxd -z b; echo bad=$?
