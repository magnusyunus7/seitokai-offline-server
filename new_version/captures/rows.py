import msgpack, sys
d = msgpack.unpackb(open(sys.argv[1], "rb").read(), raw=False, strict_map_key=False)
for i, r in enumerate(d["080001"]): print(i, r)