import hashlib
from build_site_data import verified_translation_entry

def candidate(source,text):
    return {"source_sha256":hashlib.sha256(source.encode()).hexdigest(),"text":text}

def main():
    details={"description":"English   source", "game_features":["one","two"],"repack_features":["keep"]}
    entry={"description":candidate("English source","FR"),"game_features":{"0":candidate("one","un"),"1":candidate("old","obsolete"),"2":candidate("extra","extra")},"repack_features":{"0":candidate("keep","non")}}
    actual,count=verified_translation_entry(details,entry)
    assert count==2 and actual=={"description":entry["description"],"game_features":{"0":entry["game_features"]["0"]}}
    assert verified_translation_entry({},entry)==({},0)
    assert verified_translation_entry(details,None)==({},0)
    assert details["description"]=="English   source"
    print("translation build source hash, stale fields and fallback OK")
if __name__=="__main__": main()
