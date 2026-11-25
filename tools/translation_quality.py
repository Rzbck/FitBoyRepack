"""Bounded, conservative quality checks for English-to-French game prose."""
from collections import Counter
import re

QUALITY_VERSION=2
RETRY_LIMIT=6
# Only relatively unambiguous phrases, not individual polysemous words.
GLOSSARY={
    "Nintendo Switch":"Nintendo Switch","PlayStation":"PlayStation","Xbox":"Xbox",
    "Steam Deck":"Steam Deck","Unreal Engine":"Unreal Engine","DirectX":"DirectX",
    "Yuzu Emulator":"émulateur Yuzu","sugar glider":"phalanger volant",
    "bullet hell":"bullet hell","skill tree":"arbre de compétences",
    "skill trees":"arbres de compétences","party-building skills":"compétences de constitution d'équipe",
    "couch co-op":"coopération locale","couch-co-op":"coopération locale",
    "split-screen":"écran partagé","open world":"monde ouvert",
    "dedicated servers":"serveurs dédiés","dedicated server":"serveur dédié",
    "early access":"accès anticipé","DLC":"DLC","FPS":"FPS",
}
# Only confirmed, unambiguous legacy mistakes. No broad rewrite of valid text.
LEGACY_FIXES={
    "Nintendo Switch":(r"Nintendo Commutateur","Nintendo Switch"),
    "bullet hell":(r"enfer de balles?","bullet hell"),
    "sugar glider":(r"planeur (?:de|à) sucre","phalanger volant"),
    "party-building skills":(r"compétences tactiques et de fête","compétences tactiques et de constitution d'équipe"),
}

def pattern(term):
    return r"(?<!\w)"+re.escape(term)+r"(?!\w)"

def protected_spans(text,terms):
    # Longest match wins; known titles take precedence on ties.
    rules=[(x,x,0) for x in terms if x]
    rules += [(x,y,re.I) for x,y in GLOSSARY.items()]
    rules += [("Satisfactory","Satisfactory",0),("Forager","Forager",0)]
    matches=[]
    for term,target,flags in sorted(rules,key=lambda x:-len(x[0])):
        for m in re.finditer(pattern(term),text,flags):
            if any(m.start()<end and m.end()>start for start,end,_ in matches):continue
            matches.append((m.start(),m.end(),target if flags else m.group()))
    return sorted(matches)

def mask(text,terms):
    spans=protected_spans(text,terms)
    pieces=[];mapping={};pos=0
    for i,(start,end,value) in enumerate(spans,1):
        marker=f"ZXQ{i:02d}QXZ"
        pieces.extend([text[pos:start],marker])
        mapping[marker]=value;pos=end
    pieces.append(text[pos:])
    return "".join(pieces),mapping

def required_terms(text,terms):
    return Counter(value for _,_,value in protected_spans(text,terms))

def numbers(text):
    # Normalize thousands separators and decimal commas; keep signs/units separate.
    text=re.sub(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?:\D|$))","",text)
    text=re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))","",text)
    return Counter(x.replace(",",".") for x in re.findall(r"\d+(?:[.,]\d+)?",text))

def fidelity_issue(source,target,terms):
    for name,count in required_terms(source,terms).items():
        if len(re.findall(pattern(name),target,re.I))<count:
            return "protected terminology missing"
    if numbers(source)!=numbers(target):
        return "numeric fidelity mismatch"
    if re.search(r"\b(?:never|without|not|cannot)\b|n['’]t\b",source,re.I) and not re.search(r"\b(?:jamais|sans|pas|aucun(?:e)?|ni|impossible|incapable|non|nul(?:le)?|dépourvu(?:e)?)\b",target,re.I):
        return "possible missing negation"
    return None

def repair_legacy(source,target):
    for term,(bad,replacement) in LEGACY_FIXES.items():
        if not re.search(pattern(term),source,re.I):continue
        def replace(m):
            return replacement[0].upper()+replacement[1:] if m.group()[0].isupper() else replacement
        target=re.sub(r"(?<!\w)"+bad+r"(?!\w)",replace,target,flags=re.I)
        if term=="bullet hell":
            target=re.sub(r"\bd['’]bullet hell\b","de bullet hell",target,flags=re.I)
            target=re.sub(r"\bcet bullet hell\b","ce bullet hell",target,flags=re.I)
    return target
