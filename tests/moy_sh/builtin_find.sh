mkdir -p d/a/b d/c; echo x > d/one; echo y > d/a/k.txt; echo z > d/a/b/m.txt; echo w > d/c/n.log
find d
find d -type f
find d/ -type d
find d -name '*.txt'
find d -name '[km]*' -type f
find d -name '[!a-m]*'
find d -name 'd'
cd d; find; find . -name 'n.???'; cd ..
find d/one d/c
find nosuch; echo missing=$?
find d -bogus; echo usage=$?
find d -type x; echo type=$?
find d -name; echo name=$?
