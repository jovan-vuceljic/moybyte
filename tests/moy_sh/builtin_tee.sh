printf 'hi\n' | tee one two
cat one two
printf 'more\n' | tee -a one > /dev/null
cat one
printf 'no newline' | tee three; echo
cat three; echo
printf 'x\n' | tee nodir/file; echo status=$?
tee < /dev/null; echo empty=$?
tee -z; echo bad=$?
