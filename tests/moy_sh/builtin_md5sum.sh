printf 'abc' > abc
: > empty
i=0; while [ $i -lt 100 ]; do printf '0123456789'; i=$((i+1)); done > k
md5sum abc
printf 'abc' | md5sum
md5sum abc nosuch empty; echo status=$?
md5sum - < k
md5sum k
md5sum -z abc; echo bad=$?
