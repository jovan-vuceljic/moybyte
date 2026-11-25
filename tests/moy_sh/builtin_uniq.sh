printf 'a\na\nb\nc\nc\nc\na\n' > f
uniq f
uniq -c f
uniq -d f
uniq -u f
uniq -cd f
printf 'x\nx' | uniq -c
printf '\n\nz\n' | uniq -c
printf '' | uniq; echo empty=$?
uniq nosuch; echo missing=$?
uniq f f; echo usage=$?
uniq -z f; echo bad=$?
