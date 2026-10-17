import msgpack
d = msgpack.unpackb(open(r"api_bodies\004_POST_resp.bin","rb").read(), raw=False, strict_map_key=False)["020001"]
for e in d["episode_list"]: print("episode", e["episode_id"], e["title"], e["chapter_num"])
for c in d["chapter_list"]: print(c["id"], "ep", c["episode_id"], "order", c["order"], "tickets", c["tickets"], "uid", c["uid"])