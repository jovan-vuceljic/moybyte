printf 'abc' > abc
: > empty
i=0; while [ $i -lt 100 ]; do printf '0123456789'; i=$((i+1)); done > k
sha256sum abc
printf 'abc' | sha256sum
sha256sum abc nosuch empty; echo status=$?
sha256sum - < k
sha256sum k
sha256sum -z abc; echo bad=$?
