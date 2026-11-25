import tempfile
from pathlib import Path
from translation_quality import mask, fidelity_issue, repair_legacy, numbers, QUALITY_VERSION
import translation_autodrain as w
import export_public_translations as exporter

def test_masks():
    assert w.split_sentences("Orcs Must Die! 3 is here. Play now!",["Orcs Must Die! 3"])==["Orcs Must Die! 3 is here.","Play now!"]
    source="Nintendo Switch and Nintendo Switch support split-screen with 40 players."
    text,mapping=mask(source,["Nintendo Switch"])
    assert len(mapping)==3 and list(mapping.values()).count("Nintendo Switch")==2
    assert "Nintendo Switch" not in text
    assert w.restore_sentence("ZXQ01QXZ et ZXQ02QXZ avec ZXQ03QXZ",mapping)[1:]==([],[])
    assert w.restore_sentence("ZXQ01QXZ ZXQ01QXZ ZXQ02QXZ ZXQ03QXZ",mapping)[1]
    assert fidelity_issue(source,"Nintendo Switch et Nintendo Switch proposent un écran partagé à 40 joueurs.",["Nintendo Switch"]) is None
    assert fidelity_issue(source,"Nintendo Switch propose un écran partagé à 40 joueurs.",[])=="protected terminology missing"
    assert fidelity_issue("Play with 40 players","Jouez avec 4 joueurs",[])=="numeric fidelity mismatch"
    assert fidelity_issue("Play without friends","Jouez avec vos amis",[])=="possible missing negation"
    assert numbers("1,000 and 2.5")==numbers("1 000 et 2,5")
    assert mask("The switchboard is ready",["Switch"])[0]=="The switchboard is ready"
    assert repair_legacy("a sugar glider","un planeur de sucre")=="un phalanger volant"
    assert repair_legacy("a plane","un planeur de sucre")=="un planeur de sucre"
    assert repair_legacy("a sugar glider","un planeur à sucre")=="un phalanger volant"
    assert repair_legacy("bullet hell","cet enfer de balle")=="ce bullet hell"
    assert repair_legacy("bullet hell","d'enfer de balle")=="de bullet hell"
    assert fidelity_issue("Like Satisfactory","Comme Satisfaisant",[])=="protected terminology missing"

def test_migration():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp);db=path/"test.sqlite3";c=w.connect_db(db)
        g={"id":"alpha","title":"Alpha Game","details":{"description":"Explore the world on Nintendo Switch with your friends and enjoy the adventure.","game_features":["Build your team with different abilities and fight against the enemies.","Explore the world with your team and fight against the creatures."]}}
        w.sync_queue(c,[g],{})
        c.execute("update translation_jobs set status='done',translated_text='Explorez le monde sur Nintendo Commutateur avec vos amis.' where field_key='description'")
        c.execute("update translation_jobs set status='rejected',last_error='old' where field_key='game_feature:0000'")
        c.commit()
        assert w.sync_queue(c,[g],{"alpha":{"developer":"New Studio"}})["changed"]==2
        assert c.execute("select status from translation_jobs where field_key='description'").fetchone()[0]=="done"
        assert w.repair_published_once(c)==1
        assert w.repair_published_once(c)==0
        assert c.execute("select translated_text from translation_jobs where field_key='description'").fetchone()[0]=="Explorez le monde sur Nintendo Switch avec vos amis."
        c.execute("update translation_jobs set status='rejected' where field_key like 'game_feature:%'");c.commit()
        assert w.schedule_quality_retries(c,1)==1
        c.execute("update translation_jobs set status='rejected' where field_key like 'game_feature:%'");c.commit()
        assert w.schedule_quality_retries(c,10)==1
        c.execute("update translation_jobs set status='rejected' where field_key like 'game_feature:%'");c.commit()
        assert w.schedule_quality_retries(c,10)==0
        assert exporter.export_snapshot(db,path/"out.json")["fields"]==1
        g["details"]["description"]+=" This source has actually changed."
        w.sync_queue(c,[g],{})
        assert c.execute("select status from translation_jobs where field_key='description'").fetchone()[0]=="pending"
        c.close()

if __name__=="__main__":
    test_masks();test_migration();print("Translation quality, bounded retry and published migration OK")
