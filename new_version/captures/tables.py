import msgpack, sys
d = msgpack.unpackb(open(sys.argv[1], "rb").read(), raw=False, strict_map_key=False)
for k in ("060001", "060002"):
    print(k)
    for r in d[k]: print(" ", r)