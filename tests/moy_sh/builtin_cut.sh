printf 'a:b:c\nd:e\nnodelim\n' > f
cut -d: -f2 f
cut -d: -f3,1 f
cut -d: -f2- f
cut -d : -f -2 f
cut -s -d: -f2 f
printf 'a\tb\tc\n' | cut -f2
printf 'hello\nab\n' | cut -c2-3
printf 'hello\nab\n' | cut -b1,5
printf 'hello' | cut -c2
printf 'a::b\n' | cut -d: -f2 | wc -c
printf '' | cut -f1; echo empty=$?
cut -f0 f; echo zero=$?
cut -f3-1 f; echo backwards=$?
cut -fx f; echo bad-list=$?
cut -d:: -f1 f; echo delim=$?
cut -d: f; echo no-list=$?
cut -f1 -c1 f; echo both=$?
cut -c1 nosuch; echo missing=$?
cut -z; echo bad=$?
