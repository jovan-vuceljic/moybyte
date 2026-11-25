p=d; i=0; while [ $i -lt 150 ]; do p=$p/a; i=$((i+1)); done; mkdir -p $p; echo x > $p/f; echo hi > d/g
find d | wc -l
find d -type f | wc -c
find d -name f | while read q; do [ "$q" = "$p/f" ] && echo the deepest file; done
du d | wc -l
du d | head -n 1 | wc -c
du -s d
echo 40 > /.interrupt; find d -name nothing; echo not-after
echo find=$?
echo 40 > /.interrupt; rm -r d; echo not-after
echo rm=$?; find d | wc -l
rm -r d; echo rm=$?; ls
