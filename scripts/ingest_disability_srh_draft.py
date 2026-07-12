"""
scripts/ingest_disability_srh_draft.py — MACHINE-DRAFTED disability-SRH content.

⚠️  READ THIS FIRST  ⚠️
------------------------
Unlike every other ingestion script, this content is **NOT from a source
document**. No Kinyarwanda disability-SRH source was available, so — with the
project owner's explicit sign-off — these short answers were DRAFTED to fill the
disability-SRH coverage gap for the 4 predefined questions.

Because it is machine-drafted health text in Kinyarwanda, every chunk is tagged:
    origin="machine_drafted"
    approved=false
    requires_clinical_review=true
    requires_translation_review=true      <- a native speaker MUST verify wording
    review_status="draft_unapproved"

Content is deliberately RIGHTS- and ACCESS-focused (equal rights, where to seek
help, how to ask for accessible services) rather than clinical, and every answer
defers medical specifics to a health worker and the 114 hotline. It must be
reviewed by a clinician AND a native Kinyarwanda speaker before approval, and is
intentionally EXCLUDED from the first production seed until then.

Usage:
    python -m scripts.ingest_disability_srh_draft --dry-run
    python -m scripts.ingest_disability_srh_draft            # embed + upsert
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:  # noqa: BLE001
    pass

from app.services.ingestion import _hash, clean_text, ingest_chunks

SOURCE = "machine_drafted_disability_srh"

# (question, drafted answer) — maps 1:1 to the predefined disability_srh
# questions in the frontend. Topic = disability_srh for all.
DRAFTS: list[tuple[str, str]] = [
    ("Ese abantu bafite ubumuga bafite uburenganzira bungana bwo kubona amakuru "
     "ajyanye n'ubuzima bw'imyororokere n'imibonano mpuzabitsina?",
     "Yego. Abantu bafite ubumuga bafite uburenganzira bungana n'abandi bwo kubona "
     "amakuru n'ubufasha ku buzima bw'imyororokere n'imibonano mpuzabitsina. Ubumuga "
     "ntibukuraho uburenganzira bwo kumenya ku mubiri wawe, kwirinda indwara, no "
     "kwifatira ibyemezo ku buzima bwawe. Aya makuru akwiye gutangwa mu buryo "
     "bworoheye buri wese — urugero mu ndimi z'amarenga ku batumva, mu nyandiko "
     "zoroshye cyangwa mu majwi. Niba ukeneye ubufasha cyangwa amakuru arambuye, "
     "ushobora kugana umujyanama w'ubuzima cyangwa uhamagare 114."),
    ("Nakoresha nte serivisi z'ubuzima bw'imyororokere n'imibonano mpuzabitsina "
     "niba nkoresha igare ry'abamugaye?",
     "Niba ukoresha igare ry'abamugaye, ufite uburenganzira bwo kubona serivisi "
     "z'ubuzima bw'imyororokere. Ushobora kubanza guhamagara ikigo nderabuzima "
     "cyangwa ivuriro rikwegereye ukabaza niba hari inzira zinjira zoroheye igare "
     "n'igihe cyiza cyo kuza. Ushobora kandi kujyana n'umuntu wizeye wagufasha. Niba "
     "serivisi runaka itaboneka ku buryo bwiza kubera imiterere y'ahantu, saba ko "
     "bakwereka aho wayibona ahandi hakwiriye. Ku bufasha cyangwa amakuru, hamagara "
     "114."),
    ("Ese hari amakuru cyangwa serivisi z'ubuzima bw'imyororokere n'imibonano "
     "mpuzabitsina zigenewe abantu batumva cyangwa bumva nabi?",
     "Yego, abantu batumva cyangwa bumva nabi bakwiye kubona amakuru y'ubuzima "
     "bw'imyororokere mu buryo bwabagenewe. Bimwe mu byabafasha ni ukugana serivisi "
     "zikoresha ururimi rw'amarenga, gusaba umusemuzi w'ururimi rw'amarenga ku kigo "
     "nderabuzima, cyangwa gukoresha amakuru yanditse n'amashusho asobanura. "
     "Ushobora kandi gusaba umuntu wizeye kugufasha gusobanukirwa. Niba ukeneye "
     "ubundi bufasha, ushobora guhamagara 114 cyangwa ukagana umujyanama "
     "w'ubuzima."),
    ("Ni nde nshobora kuganiriza ku buzima bwanjye bw'imyororokere n'imibonano "
     "mpuzabitsina nk'umuntu ufite ubumuga?",
     "Nk'umuntu ufite ubumuga, ushobora kuganira ku buzima bwawe bw'imyororokere "
     "n'imibonano mpuzabitsina n'abantu benshi bizewe: umujyanama w'ubuzima cyangwa "
     "umuforomo ku kigo nderabuzima, umuganga, ababyeyi cyangwa umuntu mukuru wizeye "
     "mu muryango, ndetse n'imiryango iharanira uburenganzira bw'abantu bafite "
     "ubumuga. Ntugire isoni — kubaza no gushaka ubufasha ni uburenganzira bwawe. Ku "
     "bibazo byihutirwa cyangwa amakuru, hamagara 114."),
]


def build_chunks() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for i, (q, a) in enumerate(DRAFTS):
        text = clean_text(f"{q}\n{a}")
        out.append({
            "id": _hash(text),
            "text": text,
            "metadata": {
                "source": SOURCE,
                "title": q,
                "topic": "disability_srh",
                "language": "rw",
                "chunk_id": f"{SOURCE}:{i}",
                "date_ingested": now,
                # Strong provenance — machine-drafted, must be reviewed twice.
                "origin": "machine_drafted",
                "approved": False,
                "review_status": "draft_unapproved",
                "requires_clinical_review": True,
                "requires_translation_review": True,
            },
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    chunks = build_chunks()
    print("MACHINE-DRAFTED disability_srh:", len(chunks), "chunks (approved=false, "
          "requires_clinical_review + requires_translation_review)")
    for c in chunks:
        print("  -", c["metadata"]["title"][:70])
    if args.dry_run:
        print("dry-run: nothing embedded or upserted.")
        return

    from app.database import Base, SessionLocal, engine
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        rep = ingest_chunks(chunks, db)
        print(f"ingested={rep['ingested']} skipped={rep['skipped']} "
              f"per_topic={rep['per_topic']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
