"""
scripts/ingest_kinyarwanda_docs.py — Ingest two manually-provided Kinyarwanda
SRH documents into the RAG knowledge base (RW side only).

Why this is a bespoke script (not the generic bulk ingester)
------------------------------------------------------------
The generic pipeline (``scripts.ingest_knowledge_base`` / ``chunk_document``)
uses a character-based ``RecursiveCharacterTextSplitter`` (500/50). That would
split a question away from its answer and merge unrelated Q&A pairs — bad for
retrieval. These two sources need *semantic* chunking:

  * Document A — a puberty/menstruation Q&A set: chunk **one Q&A pair per chunk**
    (question + its answer stay together; pairs are never merged or split).
  * Document B — cyberrwanda.org pages: chunk **per section** following the
    document's own headers, each mapped to one topic tag and its source URL.

So the chunks are built by hand here and handed to the SHARED, idempotent
``ingest_chunks()`` (embed → vector upsert → KnowledgeEntry row → JSONL cache).
No generation, no retrieval/generation-logic changes — ingestion only.

Provenance / review gate
------------------------
Every chunk is tagged (in vector metadata) ``approved=false`` /
``review_status="auto_test_unapproved"`` / ``requires_clinical_review=true`` —
identical to ``scripts.dev_seed_vector_store``. The relational row's
``reviewed_by`` stays NULL. This is the project's "staging" state: it does NOT
skip the human clinical-review gate. (Note: retrieval currently filters only on
language+topic, so staged chunks are retrievable for testing — see the summary
this script prints.)

Topic taxonomy
--------------
The KB taxonomy is the 7-class set in ``app/services/ingestion.TOPICS``. There is
no standalone "menstruation" or "gbv" tag, so:
    menstruation -> puberty      gbv -> gbv_consent

Usage
-----
    python -m scripts.ingest_kinyarwanda_docs --dry-run   # chunk + counts only
    python -m scripts.ingest_kinyarwanda_docs             # embed + upsert
    python -m scripts.ingest_kinyarwanda_docs --smoke     # + RW retrieval check

Run against a local Chroma store for safe verification (does not touch the
deployed Pinecone index):
    VECTOR_STORE_BACKEND=chroma EMBEDDING_BACKEND=local \
    CHROMA_PERSIST_DIR=./data/chroma_dev \
    DATABASE_URL=sqlite:///./data/kb_dev.sqlite \
    python -m scripts.ingest_kinyarwanda_docs --smoke
"""

from __future__ import annotations

import argparse
import sys

# Windows consoles default to cp1252 and cannot encode some characters; force
# UTF-8 so printing Kinyarwanda titles never crashes the run.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:  # noqa: BLE001
    pass

from datetime import datetime, timezone

from app.services.ingestion import _hash, clean_text  # reuse hash + cleaner

# ── Document A: puberty / menstruation Q&A set ──────────────────────────────
# Source file provided manually: "Kinyarwanda Q&A.pdf" (IBIBAZO N'IBISUBIZO).
# Each entry: (topic, question, answer). Topic uses the KB taxonomy
# (menstruation folds into "puberty"). One Q&A pair == one chunk.
DOC_A_SOURCE = "Kinyarwanda Q&A.pdf"

DOC_A: list[tuple[str, str, str]] = [
    ("puberty",
     "Ubugimbi n'ubwangavu ni iki?",
     "Ubugimbi cyangwa ubwangavu ni amagambo akoreshwa ku mpinduka z'umubiri, "
     "intekerezo n'imibanire buri muntu wese anyuramo ava mu bwana aba mukuru. "
     "Umubiri wawe unyura mu mpinduka nyinshi ziza buhoro buhoro, uko ibihe "
     "bitambuka. Ubugimbi (ku bahungu) cyangwa ubwangavu (ku bakobwa) ni "
     "icyiciro gisanzwe cy'ubuzima."),
    ("puberty",
     "Ese imihango imera ite?",
     "Buri mugore cyangwa umukobwa arihariye. Bamwe bashobora kumva ububabare "
     "budakabije mu nda mu minsi mike. Abandi bashobora kumva bananiwe cyangwa "
     "bakumva amarangamutima yahindutse. Ariko buri wese arihariye, bamwe hari "
     "igihe nta n'icyo bumva. Nujya mu mihango inshuro nyinshi, ushobora "
     "kuzajya ugira impinduka mu mubiri zigatuma umenya ko uri hafi kujya mu "
     "mihango."),
    ("puberty",
     "Kwiroteraho ni iki?",
     "Kwiroteraho biba ku bagabo cyangwa abahungu mu gihe baryamye, amasohoro "
     "agasohoka mu gitsina bitunguranye. Byitwa kwiroteraho kuko iyo umuhungu "
     "abyutse asanga ibyo yiyoroshe cyangwa ibyo yambaye byatose. Kwiroteraho "
     "ni ibintu bisanzwe kandi bikunze kubaho ku muhungu ugeze mu bugimbi "
     "cyangwa ku mugabo umaze igihe kinini adakora imibonano mpuzabitsina."),
    ("puberty",
     "Ukwezi k'umugore ni iki?",
     "Dore muri make uko bigenda: ni nk'ubufindo. Ukwezi k'umugore gutangira "
     "kuva umunsi wa mbere imihango yaziye kugeza ku wundi munsi imihango itaha "
     "izaziraho. Ukwezi k'umugore gutegura umubiri wawe gusama. Iyo udasamye "
     "urongera ukajya mu mihango. Ibi nibyo biba biri kuba mu mubiri wawe: "
     "Ufite udusabo tw'intanga tubiri, buri kamwe kagira amagi menshi. Ayo magi "
     "ni mato cyane ku buryo utayabonesha ijisho. Buri kwezi, imisemburo ifasha "
     "igi gukura. Iyo igi rikuze, biba bivuze ko rigeze igihe cyo guhura "
     "n'intangangabo. Imisemburo ifasha ingobyi yo muri nyababyeyi kubyimba no "
     "kunepa. Hagati mu kwezi kwawe, imisemburo ibwira agasabo k'intanga "
     "kurekura igi. Iki nicyo bita kujya mu gihe cy'uburumbuke. Iyo igi "
     "risohotse mu gasabo k'intanga, rinyura mu muyoborantanga, rigana muri "
     "nyababyeyi. Iyo hatabayeho gusama, umubiri wawe ntukenera ko ya ngobyi "
     "ibyimba. Igice cyabyimbye cy'iyo ngobyi kirirekura, amaraso, "
     "intungamubiri n'inyama byari bikigize bigasohokera mu gitsina. Ibyo ni "
     "byo byitwa imihango."),
    ("pregnancy",
     "Ese gutwita bigenda gute?",
     "Gutwita ni igihe intangangore yakiriye intangangabo. Mu gihe cy'imibonano "
     "mpuzabitsina, umugabo asohorera mu mugore intangangabo nyinshi, "
     "zikishakira inzira igana ku ntangangore ngo zihure nayo. Iyo intangangabo "
     "imwe muri zo ihuye n'intangangore bikora igi ubwo umugore akaba yasamye. "
     "Iryo gi rishaka aho rifata muri nyababyeyi, umwana agatangira kwirema mu "
     "gihe cy'amezi icyenda."),
    ("puberty",
     "Inshuti zanjye zose zifite amabere, kuki njye ataramera?",
     "Ubugimbi cyangwa ubwangavu, ntibwitura aho ako kanya. Buza mu byiciro "
     "bitandukanye, binatwara imyaka myinshi. Ushobora kugaragaza ibimenyetso "
     "byabwo ukiri muto, abandi bakabigaragaza nyuma. Buri wese afite umubiri "
     "wihariye, buri wese ajya mu bugimbi cyangwa ubwangavu mu bihe byihariye."),
    ("puberty",
     "Kuki abakobwa bakura vuba kuruta abahungu?",
     "Ubusanzwe abakobwa binjira mu bwangavu mbere y'uko abahungu bajya mu "
     "bugimbi. Ibi akaba ari yo ntandaro y'ubusumbane mu gihagararo. Niba uri "
     "umukobwa ukaba usumba abahungu mwigana, ahubwo hagarara weme neza, maze "
     "wishimire kuba muremure! Niba uri umuhungu ukaba wifuza kuba muremure, "
     "humura nta rirarenga, wenda uzakomeza gukura mu gihagararo."),
    ("puberty",
     "Ni iki nakora igihe ukwezi kwange guhindagurika?",
     "Nta gitangaje kuba wagira imihango ihindagurika igihe runaka mu buzima "
     "bwawe, cyane cyane iyo ugitangira kujya mu mihango. Ahubwo, ni ibisanzwe "
     "cyane kugira imihango ihindagurika mu myaka mike ya mbere. Bimwe mu "
     "biranga ukwezi guhindagurika harimo: Kubura imihango, imihango iza mbere "
     "cyangwa nyuma, kugira ibimenyetso bitandukanye biteguza kuza kw'imihango, "
     "kuva bikomeye cyangwa byoroheje ugereranyije n'ibindi bihe, kuva iminsi "
     "myinshi, kutamenya igihe ugira mu mihango cyangwa bigahinduka buri kwezi. "
     "Bamwe bagira imihango ihindagurika mu buryo buhoraho. Niba ibihe byinshi "
     "ugira imihango ihindagurika, utamenya igihe izazira, cyangwa ukabona "
     "iraza ku buryo budasanzwe, wagana muganga akareba ko nta kindi kibazo "
     "kibitera."),
    ("puberty",
     "Kuki umubiri wanjye uri guhinduka?",
     "Mu gihe cy'ubugimbi cyangwa ubwangavu, ubwonko bwacu bwifashisha "
     "imisemburo maze bukohereza ubutumwa mu bindi bice by'umubiri bubisaba "
     "gukura no guhinduka. Imisemburo imwe n'imwe ibwira imibiri yacu gutangira "
     "kumera ubwoya ahantu hashya nko mu kwaha no mu bice by'ibanga, iyindi "
     "ikabwira imibiri yacu gutangira kubaho nk'abantu bakuru."),
    ("puberty",
     "Mpora ndakaye kandi mbabaye iteka, ubwo naba mfite ikihe kibazo?",
     "Oya. Nta kibazo ufite. Umubiri wawe wose uri gukura unahinduka. Nta "
     "gitangaje na kimwe ko ibyiyumviro n'amarangamutima yawe nabyo biri "
     "guhinduka. Rimwe na rimwe ushobora kugira uburakari cyangwa akababaro "
     "kenshi, wigira ikibazo, n'abandi bantu bakuru byababayeho, kandi "
     "uzabisobanukirwa. Nta kibazo kuba wabiganiriza umuntu mukuru ufitiye "
     "icyizere nk'umuvandimwe wawe cyangwa undi wizeye."),
    ("puberty",
     "Imihango ni iki?",
     "Imihango ni uburyo karemano bwo gusohora ingobyi yakuriraga muri "
     "nyababyeyi yawe. Iki ni igice kimwe mu bigize ukwezi k'umugore. Mu gihe "
     "cy'ukwezi kwawe, udusabo tw'intanga twohereza igi rito, hanyuma "
     "nyababyeyi yawe ikabyibuha, ikitegura kwakira no kubungabunga umutekano "
     "w'iryo gi. Iyo hatabayeho imibonano mpuzabitsina ngo iryo gi rihure "
     "n'intanga-ngabo (ibyo bita gusama), ntiriguma muri nyababyeyi ahubwo iryo "
     "gi n'ibyagombaga kuritunga birasohoka bisa nk'amaraso. Ibi nibyo byitwa "
     "imihango, akaba ariyo mpamvu uva amaraso buri kwezi."),
    ("pregnancy",
     "Kuki umuntu atajya mu mihango iyo atwite?",
     "Iyo usamye, umubiri wawe ukenera ya ngombyi yo muri nyababyeyi mu gufasha "
     "urusoro gukura. Ni yo mpamvu utajya mu mihango mu gihe utwite. Imihango "
     "igaruka nyuma."),
    ("puberty",
     "Ndi kubabara cyane mu gihe cy'imihango, nkore iki?",
     "Ihangane kuba umerewe gutyo. Gusa nyine, hari abagore cyangwa abakobwa "
     "bagira ububabare bumara umunsi umwe cyangwa ibiri buri uko bagiye mu "
     "mihango. Kuruhuka bishobora kugufasha kugabanya ububabare. Igihe uri "
     "kubabara cyane, gerageza gufata ibinini bigabanya ububabare, ariko "
     "ntubikoreshe kenshi. Ibintu bishyushye nk'icyayi cyangwa isosi bishobora "
     "nabyo kugufasha, cyangwa gushyira agacupa karimo amazi ashyushye mu "
     "mugongo cyangwa ku nda ahari kubabara. Mu gihe ububabare bumara iminsi "
     "myinshi buri kwezi, cyangwa se imiti wafashe ntacyo ikumarira, jya kwa "
     "muganga agasuzume, arebe ko nta bundi burwayi ufite, anaguhe ubufasha "
     "harimo kukwandikira indi miti yagufasha kurushaho kumererwa neza. "
     "Ntukwiye kwivura magendu igihe imiti isanzwe igabanya ububabare itari "
     "gukora, gana muganga agufashe."),
    ("puberty",
     "Imisemburo ni iki?",
     "Tekereza imisemburo nk'uburyo umubiri wacu uhanahana amakuru. Imisemburo "
     "ni ibintu bisanzwe mu mubiri bikura amakuru mu bice bimwe biyajyana mu "
     "bindi. Mu bugimbi/bwangavu, agace gato ko mu bwonko bwacu gashinzwe "
     "kumenyesha umubiri gukora imisemburo, karekura imisemburo ishinzwe "
     "kumenyesha umubiri ko ugeze igihe cyo gukura no guhinduka."),
    ("puberty",
     "Ni kuki abahungu barwara ibiheri cyangwa ibishishi mu maso?",
     "Ibiheri cyangwa ibishishi bibaho igihe utwengehu (ku ruhu) twabyimbye, "
     "tugahisha, tugahinda umuriro, ndetse rimwe na rimwe tukababaza. Abakobwa "
     "n'abahungu bombi bashobora kubirwara. Ibiheri biterwa no guhindagurika "
     "kw'imisemburo y'umubiri, kwiyongera kw'amavuta yo mu ruhu, cyangwa se "
     "bagiteri."),
    ("pregnancy",
     "Ni ryari nasama mu gihe cy'ukwezi k'umugore?",
     "Amahirwe yo gusama ariyongera uko wegereza iminsi y'uburumbuke, igihe "
     "agasabo k'intanga karekuye igi rikuze. Iyi minsi yitwa iy'uburumbuke. "
     "Iminsi y'uburumbuke itangira ku munsi wa 14 mbere y'imihango. Ariko "
     "biratandukana ku bantu. Ushobora kujya mu bihe by'uburumbuke mbere "
     "cyangwa nyuma bitewe n'uko ukwezi kwawe kureshya."),
    ("puberty",
     "Imihango izamara igihe kingana iki?",
     "Mu busanzwe imihango imara hagati y'iminsi ibiri n'irindwi, kandi ikaza "
     "rimwe mu kwezi. Nurenza icyumweru ukibona amaraso uzajye kwa muganga "
     "barebe ko nta kibazo ufite. Rimwe na rimwe ukwezi gushobora gushira "
     "utabonye imihango cyangwa ukava ku buryo budasanzwe, ariko hari igihe ibi "
     "biba n'ikimenyetso cy'uko wasamye. Ubaye warakoze imibonano mpuzabitsina "
     "udakoresheje agakingirizo kandi nta n'ubundi buryo ukoresha ngo udasama, "
     "wajya kwa muganga cyangwa ugakoresha agakoresho gasuzuma gusama."),
    ("puberty",
     "Nzakore iki ninjya mu mihango?",
     "Mu gihe ubonye imihango bwa mbere, simbuka wishime. Umubiri wawe uri "
     "guhinduka, uri kujya mu cyiciro cy'abakuze! Igiteye amatsiko ni iki: "
     "Ntiwamenya igihe uzagira mu mihango. Ni byiza rero ko wakwitwaza "
     "kotegisi/pad cyangwa izindi mpapuro z'isuku zabugenewe mu gikapu cyawe, "
     "witegura ko hari igihe yaza utari mu rugo. Kotegisi ifata ku ikariso "
     "yawe igafata amaraso. Ushobora kubwira mama cyangwa papa wawe, cyangwa "
     "undi muntu mukuru wizeye ko watangiye kujya mu mihango, ko ukeneye kugura "
     "kotegisi."),
    ("puberty",
     "Ni ryari ubugimbi/ubwangavu butangira?",
     "Ubusanzwe, ubugimbi n'ubwangavu butangira hagati y'imyaka 9 na 14. "
     "Birasanzwe, bibabo mu buzima kandi buri wese aca muri icyo gihe. "
     "Ubusanzwe abakobwa binjira mu bwangavu mbere y'igihe abahungu batangirira "
     "ubugimbi."),
    ("puberty",
     "Ese nshobora gukoresha isabune n'amavuta mu kwita ku isuku y'igitsina cyange?",
     "Oya. Igitsina cyawe gifite uburyo bwo kwikorera isuku udakoresheje "
     "ibikoresho bihenze. Ibyo ukeneye ni ugusukura umubiri wawe wose n'isabune "
     "n'amazi."),
    ("puberty",
     "Kuki abakobwa baribwa mu nda iyo bari mu mihango?",
     "Abakobwa bamwe bagira uburibwe iyo bari mu mihango kubera ko imisemburo "
     "imwe itera umura kwikamura kugira ngo usohore amaraso aribyo twita "
     "imihango. Ntabwo abakobwa bose baribwa muri iki gihe, gusa ni ibisanzwe "
     "ko umukobwa yagira uburibwe no kumva abangamiwe mu gihe ari mu mihango. "
     "Ntabwo ukwiye guhangayika mu gihe bikubayeho ariko niba wumva ufite "
     "uburibwe bukabije, ushobora gufata ibinini bya Ibuprofen cyangwa "
     "paracetamol bikakorohereza."),
    ("puberty",
     "Ese kuva amaraso gutya nta ngaruka byagira?",
     "Mu ntangiriro uba wumva bidasanzwe, ariko kujya mu mihango nta nkeke "
     "biteye. Niba uhangayikishijwe nabyo, uzaganire n'umuganga cyangwa "
     "umuforomo bazaguha amakuru ukeneye."),
    ("puberty",
     "Ni gute namenya ko nageze mu bugimbi/ubwangavu?",
     "Ubwangavu cyangwa ubugimbi ntibubaho umunsi umwe. Ibuka ko twavuze ko "
     "butangira iyo agace k'ubwonko gashinzwe kumenyesha umubiri ko ukwiye "
     "gukora imisemburo gatangiye gusohora imisemburo. Iyo misemburo igatanga "
     "ubutumwa ku mubiri wose ko ugomba gukura no guhinduka. Izo mpinduka "
     "zigenda ziyongera zigafata umwanya munini. Ushobora kubona ko uri gukura, "
     "cyangwa uri kumera ubwoya ahantu hashya, cyangwa ko watangiye kujya mu "
     "mihango cyangwa watangiye kwiroteraho. Ibyo byose rero ni impinduka zo mu "
     "bugimbi n'ubwangavu."),
    ("puberty",
     "Ni irihe tandukaniro riri hagati y'imihango n'ukwezi k'umugore?",
     "Kujya mu mihango ni kimwe mu bice bigize ukwezi kwawe. Iyo hatabayeho "
     "gusama, umubiri wawe ntuba ugikeneye ibyo wari warateguye kugira ngo "
     "bitunge umwana, bityo rero birashwanyuka, maze amaraso n'ibindi byari "
     "biyigize bigasohokera mu gitsina. Ibyo ni byo byitwa imihango! Naho "
     "ukwezi ku mugore ni igihe kiri hagati y'umunsi wa mbere w'imihango kugeza "
     "ku munsi wa nyuma ubanziriza imihango izakurikiraho. Ku bisobanuro "
     "birambuye ku mihango yawe, reba ikibazo mu bugimbi n'ubwangavu kibaza "
     "\"Imihango ni iki?\""),
    ("puberty",
     "Ese abandi bashobora kubyibwira mu gihe ndi mu mihango?",
     "Oya. Ntabwo abantu bamenya ko uri mu mihango. Ntabwo umuntu yareba "
     "umukobwa ngo ahite amenya ko ari mu mihango, cyangwa ko ari kuva amaraso. "
     "Ibi bivuze rero ko nta mpamvu yo kugira icyo uhindura ku buryo wari "
     "usanzwe ubayeho kubera ko uri mu mihango. Ntibyakubuza kujya ku ishuri "
     "cyangwa gukomeza imirimo yawe ya buri munsi, uko byagenda kose."),
    ("puberty",
     "Ni ibihe byiza byo gukoresha tampon kurusha pad?",
     "Tampons na pads byombi bifite ibyiza n'ibibi. Abakobwa benshi bahitamo "
     "gukoresha pad iyo bagitangira kujya mu mihango kuko zoroshye "
     "gukoreshwa. Ikindi kiza ni uko ubasha kubona amaraso yagiyeho kugira "
     "umenye igihe cyo guhindura. Gusa abandi bakobwa nanone bahitamo gukoresha "
     "Tampon kuko bashobora kuzambara bagakora sport ntacyo bikanga ndetse "
     "bakaba banakoga muri piscine. Ikindi kandi, abakobwa bamwe na bamwe, "
     "bahitamo tampon kuko zoroshye kubikwa mu dukapu ndetse no mu mufuka "
     "w'umwenda. Ikindi kiza cya tampon ni uko umuntu ataba ayumva kuko iba iri "
     "mu mubiri imbere. Pad ishobora kubangama kuri bamwe. Icyemezo cyo "
     "gukoresha pads cyangwa tampon ni wowe ukifatira, wahitamo icyo ushaka "
     "gukoresha n'iki kunogeye. Abakobwa benshi bagenda babisimburanya, rimwe "
     "na rimwe bakoresha pads bitewe n'aho bagiye n'ingano y'amaraso bari kuva. "
     "Icyo wahitamo icyo aricyo cyose, ikingenzi ni uko wibuka guhindura buri "
     "masaha atatu cyangwa ane (cyangwa igihe gito kuri icyo ukurikije ingano "
     "y'amaraso umuntu ari kuva)."),
    ("puberty",
     "Ni ryari nkwiriye gukoresha pad?",
     "Mu gihe imihango ije, ukwiriye guhita ukoresha pad. Wibuke ko mu gihe uri "
     "mu mihango ukwiye guhindura pad buri masaha 3 cyangwa ane (Cyangwa make "
     "kuri ayo mu gihe uva cyane). Byongeye kandi, mu myaka y'ubwangavu, ni "
     "ibisanzwe kuba imihango yaza mu bihe bitari ku murongo. ni byiza rero "
     "kugendana pad igihe cyose."),
    ("puberty",
     "Imihango yanjye irasanzwe?",
     "Hari abakobwa bagira ukwezi kudahinduka, ariko hari n'abagira ukwezi "
     "guhindagurika buri gihe. Ni ibisanzwe ko abakobwa bakiri bato bagira "
     "ukwezi guhindagurika. Bitewe n'uko utamenya igihe uzagira mu mihango, "
     "biranagoye kumenya igihe agasabo k'intanga kazarekurira igi (nubwo waba "
     "wita ku kumenya uko ukwezi kwawe guteye)."),
    ("puberty",
     "Nkunda gutekereza no guterwa impungenge n'ibyo abandi bantekerezaho. Impamvu yaba ari iyihe?",
     "Abantu bita cyane ku mibanire yabo n'abandi. Ni ibisanzwe ko abana, "
     "abangavu n'ingimbi cyangwa abantu bakuru bashobora gutekereza kucyo "
     "abandi babibazaho. Menya ibi ngibi: Uko uhangayikishwa no kumenya icyo "
     "abandi bagutekerezaho..., abandi nabo baba bibaza icyo ubatekerezaho. Ni "
     "uguha agaciro kanini ibintu bifite agaciro gake. Nta kosa ririmo kuba "
     "wagira isoni cyangwa igihunga, ariko ntukemere ko ibi bihindura ubuzima "
     "bwawe. Ufite ibintu byinshi byo gukora n'ahantu henshi ho kureba! "
     "Ntukemere ko imihangayiko yawe ibangamira inzira zawe."),
    ("puberty",
     "Ese nzajya mu mihango ubuzima bwanjye bwose?",
     "Abantu benshi bahagarika kujya mu mihango iyo bageze hagati y'imyaka 45 "
     "na 55. Ibi byitwa gucura. Urugendo rwo gucura rushobora gufata igihe, "
     "n'imihango ikagenda ihindura uko yazaga. Iyo umaze gucura ntiwongera "
     "gusama."),
    ("puberty",
     "Kuki ntarajya mu mihango?",
     "Buri mukobwa abona imihango mu gihe kihariye. Nta cyiza cyangwa ikibi "
     "kiri mu kujya mu mihango mbere cyangwa nyuma y'abandi bakobwa. Ibuka "
     "kandi ko mu gihe ufite impungenge cyangwa ukeneye gusobanukirwa byinshi "
     "ku mubiri wawe mwiza kandi wihariye, wasura ivuriro rikwegereye."),
    ("puberty",
     "Mpangayikishijwe n'ubwangavu/ubugimbi, ese nkore iki?",
     "Bishobora kuba byaratangiye kukubaho ariko niba bitaraba, buriya umubiri "
     "wawe ugiye gutangira kugira impinduka, haba imbere ndetse n'inyuma. "
     "Humura rwose ibi ntibizaguhangayikishe. Buriya abantu bagukikije, buri "
     "muntu mukuru ubona hafi yawe, yaba mama wawe, papa wawe, basaza "
     "(abavandimwe) bawe bakuru, uriya muntu ucuruza imbuto ku isoko, abarimu "
     "bawe, abakinnyi ba filimi ubona kuri tereviziyo, yewe na perezida ubwe, "
     "bose banyuze mu bugimbi/ubwangavu. Niba barabishoboye, nawe uzabishobora."),
    ("puberty",
     "Ni nde ukwiriye gukoresha Pad?",
     "Pad zakoreshwa n'uwariwe wese mu gihe k'imihango. Abakobwa bakoresha "
     "pads, tampons ndetse n'udukombe tw'imihango. Bashobora guhinduranya ubu "
     "buryo butandukanye bitewe n'ibyo bakunda, ndetse n'ibibaha amahoro."),
    ("puberty",
     "Ninjiye mu bugimbi/ubwangavu, ese ubwo bivuze ko niteguye gukora imibonano mpuzabitsina?",
     "Kujya mu bugimbi/bwangavu bivuze ko n'imibiri yacu iba yiteguye kuba "
     "yatera inda/yatwita, ariko ntibivuze ko twiteguye gukora imibonano "
     "mpuzabitsina, ngo dutwite cyangwa ngo dushinge imiryango. Nugera mu "
     "bugimbi/bwangavu, uzatangira kugira ibyiyumviro by'urukundo, ariko kandi "
     "ibi ntibivuze ko witeguye kuba wakora imibonano mpuzabitsina."),
    ("puberty",
     "Ese nabwirwa ni iki ko ukwezi kwange gusanzwe (nta kibazo kirimo)?",
     "Ukwezi k'umugore kubarwa uhereye igihe wagiriye mu mihango kugeza igihe "
     "uzagira mu mihango itaha. Ugereranyije ni hagati y'iminsi 25 na 30 ariko "
     "gushobora no kuba guto kukagira 21 cyangwa kurekure kukageza ku minsi 35. "
     "Biratandukanye kuri buri muntu. Umubare w'iminsi ushobora no kutaba umwe "
     "buri kwezi. Iyo uri mu mihango, birasanzwe kuva amaraso mu gihe c'iminsi "
     "iri hagati y'ibiri n'irindwi. Amaraso ashobora kuba arekuye cyangwa "
     "afashe, kandi ashobora guhindura ibara akaba umutuku wijimye, wererutse "
     "cyangwa agasa n'iroza."),
    ("gbv_consent",
     "Ese guca imyeyo ni iki? Bifite akahe kamaro? Bifite izihe ngaruka?",
     "Guca imyeyo ni ugukurura ibice by'umwinjiriro w'igitsina. Bivugwa ko uyu "
     "muhango wongerera uburyohe abagabo n'abagore mu gihe bari gukora "
     "imibonano mpuzabitsina. Nubwo ibi bishingiye ku muco ariko, ntaho "
     "bihuriye no gukorwa neza kw'imibonano mpuzabitsina. Zimwe mu ngaruka zo "
     "guca imyeyo zirimo ububabare, kubangamirwa, isuku nke, kocyerwa no kuba "
     "wakomereka. Guca imyeyo bikunze gukorerwa abana b'abakobwa kandi "
     "batabihisemo. Wowe nk'umukobwa rero ufite uburenganzira bwo kwanga ko "
     "bigukorerwa igihe utabishaka. Ufite uburenganzira bwo kwifatira "
     "umwanzuro. Guca imyeyo bikorwa ku bushake kandi wabikora cyangwa "
     "utabikora, uryoherwa n'imibonano mpuzabitsina."),
    ("puberty",
     "Ni ryari nzabona imihango yanjye ya mbere?",
     "Buri muntu arihariye. Ikigero cy'imyaka abakobwa bagira mu mihango bwa "
     "mbere ni hagati y'imyaka 11 na 15 ariko bishobora no kubaho mbere cyangwa "
     "nyuma y'iyo myaka. Nta buryo buhamye bwo kugena igihe uzaboneraho "
     "imihango yawe. Umunsi umwe, uzabyuka ubone amaraso ku mashuka yawe, "
     "cyangwa uyabone ku mwenda wawe, ni uko biteye! Nibibaho rero, ntuzagire "
     "ubwoba cyangwa ipfunwe, iki ni icyiciro gisanzwe cy'ubuzima "
     "bw'umugore wese."),
    ("puberty",
     "Ni ubuhe bwoko bundi bw'ibikoresho by'isuku bikoreshwa mu gihe cy'imihango?",
     "Ukuyeho Pads na Tampon, hari ibindi bikoresho by'isuku ushobora gukoresha "
     "mu gihe cy'imihango harimo amakariso yagenewe imihango ndetse n'udukombe "
     "duto dukoze muri plastike. Ikariso yagenewe imihango ni ikariso iba imeze "
     "nk'ibisanzwe, uretse ko ifite cotton nyinshi ku buryo ibasha gufata "
     "imihango. Hari ubwoko butatu bw'amakariso yagenewe imihango. Ubwoko "
     "bumwe ni ubwagenewe imihango mike, ubwa kabiri ni ubwagenewe imihango "
     "iringaniye, ubwa gatatu ni ubwagenewe imihango myinshi. Udukombe "
     "twagenewe imihango: Ni udukombe duto tumeze nk'inzogera, dukoze muri "
     "plastike yorohereye kandi dukweduka. Winjiza aka gakombe mu gitsina gore, "
     "hanyuma kakajya kajyamo amaraso. Utwinshi muri utu dukombe dushobora kozwa "
     "tukongera tugakoreshwa. Hari utundi dukombe duto dukoreshwa rimwe gusa "
     "uhita ujugunya umaze kudukoresha cyangwa nyuma y'imihango. Kumenya "
     "igikoresho cy'isuku wakoresha mu gihe cy'imihango ni amahitamo yawe."),
    ("puberty",
     "Ese ubugimbi/ubwangavu buvuze ko ubu nabaye umuntu mukuru ku buryo bwuzuye?",
     "Oya. Ubugimbi n'ubwangavu bugaragaza ko uri kuba mukuru. Ibice "
     "bitandukanye by'umubiri wawe birahinduka mu bihe bitandukanye. Ntibivuze "
     "ko ubwo wameze amabere cyangwa ubwoya ku bindi bice, cyangwa wanize ijwi, "
     "ubwonko bwawe bwakiriye izo mpinduka. Utangiye kuba mukuru, tegereza "
     "bizagenda neza."),
    ("puberty",
     "Nakoresha kotegisi n'izindi mpapuro zabugenewe mu gihe cy'imihango?",
     "Ni wowe ugomba guhitamo. Kotegisi ni igipapuro cy'isuku ufatisha ku "
     "ikariso yawe kikagumaho. Tampo, ni akantu gato winjiza imbere mu gitsina "
     "cyawe kakanyunyuza imihango. Amahitamo uko ari abiri ni meza kandi atanga "
     "umutekano, ariko ugomba kwibuka kubihindura hagati y'amasaha 4 na 6 "
     "bitewe n'ingano y'amaraso uva."),
    ("puberty",
     "Kuki abantu bamwe baterwa ipfunwe no kujya mu mihango?",
     "Buri mukobwa ajya mu mihango. Ni ibisanzwe biba ku bantu nta n'impamvu yo "
     "kugira ipfunwe kubera imihango. Ni kimwe mu bikwereka ko wakuze. Mama "
     "wawe, ba nyogosenge, bakuru bawe ndetse na benshi mu nshuti zawe "
     "babibayemo cyangwa bazabibamo vuba. Hari abantu benshi rero wagana "
     "mukaganira, ukababwira uko wumva iby'imihango yawe."),
    ("puberty",
     "Ese birasanzwe ko umukobwa azana ururenda rw'umweru mu gitsina?",
     "Ni ibisanzwe ko abakobwa bazana ururenda rw'umweru mu gitsina, ni uburyo "
     "umubiri wo ubwawo ukoresha mu kubobeza no gusukura igitsina gore ndetse "
     "no kukirinda indwara. Ingano, impumuro ndetse n'ibara ry'urwo rurenda "
     "biterwa n'igihe ugezemo mu kwezi kwawe. Iyo ruhinduye ibara, impumuro "
     "cyangwa se rukagutera kwishimagura, biba byiza ugiye kwa muganga "
     "bakakurebera niba nta kibazo kirimo."),
    ("puberty",
     "Kuki guhera ku myaka cumi n'ibiri abahungu bashyukwa buri munsi ndetse na buri gihe iyo babonye umukobwa? Ni ibisanzwe?",
     "Ni ibisanzwe ko abahungu b'ingimbi bashyukwa kubera ko imisemburo yabo "
     "iba yiyongera, ibi bikagira ingaruka ku mibiri yabo n'ibyiyumviriro "
     "byabo. Gushyukwa kw'ingimbi ni ibisanzwe kandi ibi by'iyumviro biraza "
     "bikanagenda igihe icyo aricyo cyose. Hari abahitamo kwikinisha kugira ngo "
     "ubwo bushake bushire. Nutekereza gukora imibonano mpuzabitsina, uzegere "
     "umuganga muganire ku buryo wakoresha wirinda gutera inda utateguye "
     "cyangwa kwandura indwara zandurira mu mibonano mpuzabitsina."),
    ("puberty",
     "Wamenya gute ko imyanya myibarukiro yawe ikora, neza mbese ko wabasha kubyara?",
     "Mu myaka y'ubwangavu, imisemburo itandukanye ituma habaho impinduka "
     "imbere n'inyuma ku mubiri. Iyi misemburo ni nayo ituma imyanya "
     "myibarukiro yawe ikura bihagije ku buryo umuntu aba ashobora kuba yasama, "
     "ndetse akanabyara. Ku bahungu, bamera ubwoya ku myanya ndangagitsina "
     "(Insya), ijwi rigahinduka, umubiri wabo ugatangira gukora intanga ngabo "
     "bagatangira kwiroteraho no kugira ubushake bwo gukora imibonano "
     "mpuzabitsina. Abakobwa batangira kujya mu mihango, bakazana amabere, "
     "bakamera ubwoya ku myanya ndanga gitsina yabo (Insya) ndetse bagatangira "
     "kugira ubushake bwo gukora imibonano mpuzabitsina. Izi mpinduka zose "
     "zerekana ko imyanya ndangagitsina yakuze kandi umuntu ashobora gutera "
     "cyangwa guterwa inda."),
    ("pregnancy",
     "Ese abakundana bahuje ibitsina batwita?",
     "Yego, abakundana bahuje igitsina bashobora kugira umwana. 1. Iyo ari "
     "umugore n'undi mugore, bagomba kumvikana uzatanga igi, akanatwita. Nyuma "
     "nibwo bashobora kugura intanga ngabo, cyangwa bakabisaba inshuti cyangwa "
     "umuvandimwe. Kugira ngo uyu mugore asame, aterwa intanga, aho umuganga "
     "ashyira intanga ngabo bahisemo muri nyababyeyi y'umugore uzatwita; ibi "
     "bigomba gukorwa mu gihe cy'uburumbuke kugira ngo abashe gusama. 2. Iyo "
     "ari umugabo n'undi mugabo, bombi bagira intanga ubwo bagomba guhitamo "
     "uzatanga intanga, hanyuma bagashaka igi n'umugore uzatwita iyo nda. "
     "Abagabo benshi bakundana n'abandi bagabo bakoresha igi riturutse ku wundi "
     "muntu n'umubyeyi uzatwita iyo nda; ashobora kuba ari inshuti, "
     "umuvandimwe, cyangwa umugore ukodeshejwe akaboneka binyuze mu kigo "
     "cyabugenewe. Iyo umugore uzatwita ari nawe uzatanga igi, kugira ngo asame "
     "aterwa intanga. Bishobora nanone gukorerwa ku bitaro, aho igi rihuzwa "
     "n'intanga muri laboratwari, hanyuma urusoro bakarushyira muri nyababyeyi "
     "y'umugore uzatwita iyo nda."),
    # KEPT copy of the near-duplicate "missing periods for 2 months" pair.
    # The second, near-identical copy (…"imiti irinda gusama irimo imisemburo"…)
    # is intentionally OMITTED per the dedup instruction — see MODULE note.
    ("puberty",
     "Ese birasanzwe kuba wabura imihango amezi abiri akurikirana nta mibonano mpuzabitsina wakoze?",
     "Kubura imihango ni ibisanzwe cyane cyane mu myaka ibiri ibanza ugitangira "
     "kujya mu mihango. Ibi biterwa n'uko umubiri uba ukirimo gushaka uburyo "
     "umenyera impinduka. Kubura imihango bishobora guterwa n'impamvu nyinshi "
     "zirimo, kuba waba utwite, kuba ufite umuhangayiko ukabije, impinduka nini "
     "mu biro byawe cyangwa se kuba wakoresheje imiti irinda gusama ikoresheje "
     "imisemburo. Uramutse ubuze imihango mu gihe cy'amezi 3-6, jya ku kigo "
     "nderabuzima kikwegereye, bagusuzume."),
    ("puberty",
     "Pad na Tampon ni iki?",
     "Tampons na pads ni ibikoresho bibiri bikunze kwifashishwa n'abakobwa mu "
     "gihe bari mu mihango. Bashobora no kubihinduranya. Pads: Pads ni "
     "agatambaro gakoze muri cotton komekwa ku ikariso. Hari pad zikozwe ku "
     "buryo zikoreshwa rimwe zikajugunywa hari n'izindi zikozwe mu mwenda ku "
     "buryo zimeswa zikongera gukoreshwa. Tampons: Tampon ni agatambaro "
     "gakomeye gakoze muri cotton ushyira mu gitsina mu gihe cy'imihango "
     "kagafata amaraso. Hari izigira uduplastike tugufasha kukinjiza zikagira "
     "n'utugozi tugufasha kugakurura ushaka kukavanamo. Tampon ntabwo ishobora "
     "kuburira mu gitsina cyangwa ngo iheremo. Igitsina kirayifata neza ku "
     "buryo ijyamo neza kandi ikaguma mu mwanya wayo. Pad hamwe tampon byombi "
     "bikwiye guhindurwa buri masaha atatu cyangwa ane (cyangwa se kenshi "
     "bitewe n'ingano y'amaraso umukobwa ava)."),
    ("puberty",
     "Ni iki gitera kuba imihango yaza ikanga guhagarara?",
     "Kugira imihango imara igihe kinini bikunze kuba mu rubyiruko cyane cyane "
     "abagitangira igihe cy'ubwangavu. Imihango imaze igihe kirekire nk' ukwezi "
     "kumwe kugera ku mezi abiri, ntabwo biteye impungenge. Ariko ukomeje kuva "
     "birenze icyo gihe, byaba byiza ugiye kureba muganga akagusuzuma."),
    ("puberty",
     "Ni izihe mpamvu zitera kuba imihango yatinda?",
     "Ushobora gutinda kujya mu mihango kubera impamvu zitandukanye zirimo kuba "
     "wasamye, umuhangayiko ukabije (stress), uburwayi, kubyibuha cyangwa "
     "kunanuka bikabije, gukoresha uburyo bw'imisemburo bukurinda gusama, "
     "cyangwa se hashize igihe gito utangiye kujya mu mihango. Ubuze imihango "
     "mu gihe cy'amezi 3-6, ni byiza kubiganiriza umuganga akakugira inama."),
    ("puberty",
     "Ese birasanzwe ko amaraso y'imihango aza afashe cyane? Kuki iyo abakobwa bagitangira kujya mu mihango, amaraso aba afashe?",
     "Kuva amaraso afashe cyane cyangwa adafashe mu gihe cy'imihango biterwa "
     "n'umuntu kandi bigenda bihinduka uko iminsi ishira. Wibuke ko amaraso uva "
     "iyo uri mu mihango aba avanze n'uduhu twomotse kuri nyababyeyi, ndetse "
     "hashobora kuzamo n'utubumbe tw'amaraso tungana n'igiceri nabyo bikaba "
     "ntacyo bitwaye. Gusa mu gihe amaraso aza arimo ibibumbe binini bingana "
     "nk'agapfunsi cyangwa ari binini kurushaho, cyangwa se bigusaba guhindura "
     "kotegisi yuzuye buri saha, wakwihutira kureba umuganga w'abagore "
     "akakurebera ko nta kibazo kirimo. Niba utwite ukabona ibyo bibumbe "
     "by'amaraso, ni ikimenyetso mpuruza ko inda yaba igiye kuvamo, ni ngombwa "
     "kwihutira kwa muganga."),
]

# ── Document B: cyberrwanda.org pages (per-section, with source URLs) ────────
# Source provided manually: "Kinyarwanda docs.pdf". Each entry:
# (topic, section_title, source_url, text). One section == one chunk.
DOC_B_SOURCE = "cyberrwanda.org"

_U_PUB = "https://www.cyberrwanda.org/learn/education/puberty"
_U_CON = "https://www.cyberrwanda.org/learn/info/contraception"
_U_STI = "https://www.cyberrwanda.org/learn/info/stis-and-hiv-aids"
_U_MEN = "https://www.cyberrwanda.org/learn/info/menstruation"
_U_GBV = "https://www.cyberrwanda.org/learn/info/gender-based-violence"

DOC_B: list[tuple[str, str, str, str]] = [
    # — Ubugimbi (puberty) —
    ("puberty", "Ubugimbi — icyo ari cyo", _U_PUB,
     "Ubugimbi ni igihe umubiri ugeramo ugakura byihuse waba uri umuhungu "
     "cyangwa umukobwa, ukava mu kiciro cy'ubwana ugakura. Ubugimbi buterwa "
     "n'imisemburo yo mu mubiri ituma habaho impinduka zitandukanye, haba ku "
     "mubiri cyangwa se mu marangamutima. Ku bakobwa kenshi izi mpinduka "
     "zitangira hagati y'imyaka 7 kugera 13, naho ku bahungu, akenshi "
     "bigatangira ku myaka 9 kugera 15. Imyaka ishobora no gutandukana bitewe "
     "n'umuntu, kandi izi mpinduka ntizizira rimwe, bigenda biba gake gake mu "
     "bihe bitandukanye."),
    ("puberty", "Ubugimbi — impinduka zikunze kuba ku bahungu", _U_PUB,
     "Mu gihe cy'ubugimbi, abahungu baca mu mpinduka nyinshi zitandukanye. Baba "
     "barebare, bakazana amatuza. Impinduka mu ijwi: Abahungu, ijwi ryabo "
     "rirahinduka. Rigakomera, hari n'igihe basarara mu gihe ijwi riba "
     "rihinduka, ariko bihita bishira ntibitinda. Kumera ubwoya/umusatsi: "
     "Abahungu batangira kugenda bamera ubwoya ku bice bitandukanye "
     "by'umubiri. Ubwoya bumera ku myanya ndangagitsina: Imboro na testicles, "
     "mu gatuza, mu kwaha, mu maso. Iyi misatsi ntabwo imerera icyarimwe."),
    ("puberty", "Ubugimbi — impinduka zikunze kuba ku bakobwa", _U_PUB,
     "Mu gihe cy'ubwangavu, abakobwa barakura bakaba barebare, abakazana "
     "amataye. Uko umukobwa akura, umubiri we uba uri kwitegura kuba umugore no "
     "kugira ubushobozi bwo kuba yasama. Kumera amabere: Impinduka za mbere "
     "zigaragara ku mukobwa ni amabere. Atangira ari mato ameze nk'umutemeri "
     "agakomeza akura uko iminsi ishira. Ni ingenzi kumenya ko abakobwa "
     "batamerera amabere ku myaka ingana, kandi ko amabere atera bitandukanye, "
     "akanangana bitandukanye. Kujya mu mihango: Imibiri y'abakobwa itangira "
     "gukora amagi mu rwego rwo kwitegura gusama. Buri kwezi, igi iyo ridahuye "
     "n'intangangabo, nibwo umukobwa ajya mu mihango, ikamara hagati y'iminsi 3 "
     "n'irindwi. Kumera ubwoya/umusatsi: Abakobwa bamera imisatsi ku myanya "
     "ndangagitsina yabo ndetse no mu kwaha."),
    # — Kwirinda Gusama (contraception) —
    ("contraception", "Kwirinda Gusama — incamake", _U_CON,
     "Uburyo bwo kwirinda gusama, buzwi nanone nko kuboneza urubyaro ni uburyo "
     "bukoreshwa mu kwirinda gusama. Hari uburyo bwifashisha imisemburo "
     "n'ubutayifashisha; hari n'ubw'igihe gito cyangwa kirekire. Ubu buryo "
     "bushobora gukoreshwa na buri wese - harimo abakobwa n'abahungu, "
     "abashakanye n'abatarashakana, ndetse n'abafite abana cyangwa abatabafite. "
     "Bumwe mu buryo bumenyerewe ni nk'udukingirizo n'ibinini bya buri munsi."),
    ("contraception", "Kwirinda Gusama — Udukingirizo", _U_CON,
     "Hari amoko abiri y'udukingirizo: ak'abagore n'ak'abagabo. Agakingirizo "
     "k'abagabo ni ko gakunze gukoreshwa. Kambarwa ku gitsina cy' umugabo mbere "
     "yo gukora imibonano mpuzabitsina, kagatuma intanga ngabo zitagera muri "
     "nyababyei y'umugore (uterus). Aka gakingirizo gafasha mu kurinda gusama, "
     "kimwe n' indwara zandurira mu mibonano mpuzabitsina ndetse na Virusi "
     "itera Sida. Igihe gakoreshwa: Niba ushaka kwirinda gusama, ugomba "
     "gukoresha agakingirizo igihe cyose ukoze imibonano mpuzabitsina, "
     "kugirango unirinde virusi itera Sida n'izindi ndwara zandurira mu "
     "mibonano mpuzabitsina. Udukingirizo nibwo buryo bwonyine burinda gusama "
     "no kwandura virusi itera Sida n'indwara zandurira mu mibonano "
     "mpuzabitsina."),
    ("contraception", "Kwirinda Gusama — Ikinini k'Ingoboka", _U_CON,
     "Ikinini k'Ingoboka, kizwi nanone nka \"morning pill\" cyangwa \"PlanB\" "
     "ni ikinini gifatwa nyuma yo gukora imibonano mpuzabitsina idakingiye. "
     "Gikora mu buryo bwo guhagarika cyangwa gutinza gahunda yo kuba igi ryari "
     "ryiteguye guhura n'intangangabo, bihura. Ntabwo ari ngombwa ko iki kinini "
     "ucyandikirwa na muganga; ushobora kukibona ku kigo nderabuzima cyangwa "
     "muri farumasi. Igihe gakoreshwa: Ikinini k'ingoboka kigomba gufatwa vuba "
     "bishoboka mu gihe cy'amasaha 72 cyangwa iminsi 3 nyuma yo gukora "
     "imibonano mpuzabistina idakingiye. Ni ngombwa kwibuka ko ikinini "
     "k'ingoboka kitakurinda indwara zandurira mu mibonano mpuzabitsina cyangwa "
     "virusi itera Sida."),
    ("contraception", "Kwirinda Gusama — Ibinini bya Buri Munsi", _U_CON,
     "Ikinini cya buri munsi ni uburyo bwo kwirinda gusama binyuze mu "
     "misemburo. Kugirango bukore neza, ikinini gifatwa amasaha amwe buri "
     "munsi. Ibinini bya buri munsi bigomba kuba byaratanzwe n' ushinzwe "
     "ubuzima. Ibi binini ntabwo bikurinda indwara zandurira mu mibonano "
     "mpuzabitsina cyangwa Virusi itera Sida. Igihe gakoreshwa: iki kinini "
     "gishobora gukoreshwa n' umugore ushaka uburyo bworoshye bwo kwirinda "
     "gusama by'igihe gito. Ibi binini kandi bishobora kwandikirwa umugore "
     "ugira imihango iremereye kugira ngo bayoroshye kandi bagabanye n' "
     "ububabare."),
    # — Indwara Zandurira / HIV (sti_hiv) —
    ("sti_hiv", "Indwara Zandurira mu Mibonano Mpuzabitsina na virusi itera Sida — incamake", _U_STI,
     "Indwara zandurira mu mibonano mpuzabitsina (STIs) ni indwara umuntu "
     "yandura binyuze mu mibonano mpuzabitsina, yaba mu gitsina, mu kibuno, "
     "cyangwa mu kanwa. Virusi itera Sida (HIV) ni virusi itera indwara yitwa "
     "SIDA. Virusi itera Sida yandura binyuze mu guherekanya amatembabuzi "
     "n'umuntu ufite ubwandu bwa virusi itera Sida. Ibi bishobora kuba binyuze "
     "mu gukora imibonano mpuzabitsina idakingiye, mu gihe abantu basangira "
     "urushinge, cyangwa umubyeyi akayanduza umwana mbere cyangwa mu gihe cyo "
     "kumubyara."),
    ("sti_hiv", "Indwara zandurira — Chlamydia", _U_STI,
     "Chlamydia ni infection iterwa na bagiteri. Yandura binyuze mu mibonano "
     "mpuzabitsina itadunkanye nko mu gitsina, mu kibuno, cyangwa mu kanwa. "
     "Ishobora kuvurwa hakoreshejwe antibiyotike. Iyo Chlamydia itavuwe, "
     "ishobora gushyira ubuzima mu kuga. Ibimenyetso: kubabara igihe ukora "
     "imibonano mpuzabitsina, kubabara cyangwa kuriba igihe unyara, amasohoro "
     "adasanzwe ava mu gitsina cy'umugore cyangwa umugabo. Abakobwa bashobora "
     "no kumva bashaka kwishima ku gitsina."),
    ("sti_hiv", "Indwara zandurira — Imitezi", _U_STI,
     "Imitezi ni infection iterwa na bagiteri. Yandura binyuze mu mibonano "
     "mpuzabitsina itadunkanye nko mu gitsina, mu kibuno, cyangwa mu kanwa. "
     "Ishobora kuvurwa hakoreshejwe antibiyotike. Ibimenyetso: Amasohoro "
     "adasanzwe ava mu gitsina cy'umugabo cyangwa umugore, no kubabara cyangwa "
     "kuribwa igihe unyara. Abakobwa bashobora kandi kumva bashaka kwishima ku "
     "gitsina, kubabara igihe bakora imibonano mpuzabitsina, cyangwa kuva "
     "amaraso batari mu mihango."),
    ("sti_hiv", "Indwara zandurira — Genital herpes", _U_STI,
     "Herpes ni indwara yandurira mu mibonano mpuzabitsina iterwa na virusi. "
     "Herpes ntabwo ivurwa ngo ikire, ariko hari imiti ihari igabanya "
     "ibimenyetso n'ubukana bwayo. Hari ubwoko bubiri bwa herpes: iyo mu kanwa, "
     "niyo mu myanya ndagagitsina. Umuntu wanduye herpes, ashobora kugenda "
     "ayigaragaza mu bihe bitandukanya; ikunze kwandura cyane muri iki gihe. "
     "Ibimenyetso: Kuzana uduheri cyangwa ibibyimba ku minwa cyangwa ku mpande "
     "zayo. Herpes yo mu myanya ndagagitsina ishobora gutera ibiheri cyangwa "
     "ibibyimba ku mpande z'ikibuno cyangwa mu myanya ndagagitsina."),
    ("sti_hiv", "Kwirinda virusi itera Sida", _U_STI,
     "Ni ingenzi guhora wirinda virusi itera Sida. Kwipimisha nibura rimwe mu "
     "mwaka nibwo buryo bwiza bwo kubikora. Niba uri mubashobora kwandura "
     "byoroshye (wenda uryamana n'abantu barenze umwe, ukora imibonano "
     "mpuzabitsina kenshi idakingiye, cyangwa ukoresha ibiyobyabwenge bisaba "
     "kwitera inshinge), ni byiza kwipimisha buri mezi 3 kugeza kuri 6. Ubundi "
     "buryo wakwirinda ni nko: Kora imibonano mpuzabitsina ikingiye kandi uge "
     "ukoresha agakingirizo igihe cyose uyikoze. Gabanya umubare w'abantu "
     "mukora imibonano mpuzabitsina. Irinde gutizanya inshinge cyangwa ibindi "
     "bikoresho bityaye."),
    # — Imihango (menstruation -> puberty) —
    ("puberty", "Imihango — incamake", _U_MEN,
     "Mu gihe cy'ubwangavu, hari amaraso ava muri nyababyeyi y'umukobwa agaca "
     "mu gitsina. ibi ni byo byitwa imihango. Biba buri kwezi, bikamara hagati "
     "y'iminsi 3 n'irindwi. Abakobwa benshi batangira kujya mu mihango bari "
     "hagati y'imyaka 12 na 14, hari n'abajya mu mihango mbere y'icyo gihe "
     "cyangwa na nyuma y'icyo gihe, biterwa n'umubiri w'umuntu."),
    ("puberty", "Imihango — Ukwezi k'umukobwa", _U_MEN,
     "Ukwezi k'umukobwa kubarwa guhera umunsi wa mbere umukobwa agiye mu "
     "mihango kugera ku munsi agiriye mu mihango ukwezi gutaha. Ukwezi "
     "k'umukobwa akenshi kumara iminsi 28, ariko ibi bishobora gutandukana "
     "bitewe n'umubiri w'umugore. Ukwezi k'umugore kuri bamwe kuba guto kurusha "
     "aha, cyangwa kukaba kurekure ariko kenshi biba biri hagati y'iminsi 21 na "
     "35. Ni ibisanzwe kugira ukwezi guhindagurika mu gihe umubiri umenyera, "
     "bishobora gufata amezi menshi ndetse n'imyaka myinshi kugirango bijye ku "
     "murongo."),
    ("puberty", "Imihango — igice cya mbere cy'ukwezi", _U_MEN,
     "Ikiciro cya mbere cy'ukwezi k'umukobwa ni imihango, kiba hagati y'umunsi "
     "umwe n'iminsi 7. Ibi bishobora guhinduka bitewe n'umubiri w'umuntu. Muri "
     "iki gihe, umubiri w'umukobwa uba witegura kurekura igi, nyababyeyi "
     "igatangira gukora uruhu rukoze mu maraso ndetse n'umubiri."),
    ("puberty", "Imihango — Iminsi y'uburumbuke", _U_MEN,
     "Iminsi y'uburumbuke ni iminsi 12-14 mbere y'uko ujya mu mihango. Abakobwa "
     "benshi bayitangira ku munsi wa cumi na kane, ariko ukwezi kuba "
     "gutandukanye bitewe n'umubiri w'umukobwa, abagira ukwezi kugufi cyangwa "
     "kurekure bashobora kugira iminsi y'uburumbuke ku munsi utandukanye. Ni "
     "ingenzi kugira aho wandika iminsi ugira mu mihango inshuro zikurikiranya "
     "kugira ngo umenye uko ukwezi kawe kureshya. Abagore baba bafite amahirwe "
     "menshi yo gusama mu gihe cy'uburumbuke; uramutse ukoze imibonano "
     "mpuzabitsina muri iyo minsi, uba ufite amahirwe menshi yo gutwita."),
    ("puberty", "Imihango — Nyuma y'iminsi y'uburumbuke", _U_MEN,
     "Igice cya nyuma cy'ukwezi k'umukobwa gihera kenshi ku munsi wa cumi na "
     "gatanu kugera ku munsi wa 28. Mu gihe igi ryahuye n'intangangabo, umubiri "
     "uba watangiye kwitegura kwakira umwana. Mu gihe igi ritahuye "
     "n'intangangabo, ibyiteguragara kuzatunga umwana birasohoka, ariyo "
     "mihango. Umugre ahita ajya mu mihango mu kwezi gukurikira, hanyuma ukwezi "
     "kundi nako kugatangira bundi bushya."),
    # — Isuku mu gukoresha Pad (menstruation -> puberty) —
    ("puberty", "Isuku mu gukoresha Pad", _U_MEN,
     "Buri Pad ikoresha rimwe: Mu gihe ukoresha Pad, ibuka ko Pad zikoreshwa "
     "rimwe zikajugunywa. Hindura Pad buri masaha 3-4: Umuntu akwiriye "
     "guhindura pad buri masaha 3-4. Aya masaha ashobora guhinduka bitewe "
     "n'ingano y'imihango. Ni ingenzi guhindura Pad inshuro zihagije mu "
     "kwirinda ko yakuzura, amaraso akajya ku myenda inyuma. Gira isuku wirinde "
     "no kuba warwara za infections. Kujugunya Pad: Mu gihe ukuyemo Pad, yizinge "
     "neza uyishyire mu gipapuro gikoreshwa muri wese cyangwa se mu gipapuro "
     "yavuyemo, hanyuma uyijugunye muri puberi cyangwa se niba ntayihari, "
     "uyijugunye mu bwiherero bufite umwobo. Kugira isuku: Wibuke koga nibura "
     "rimwe ku munsi, no guhanagura neza imyanya yawe ndagagitsina buri uko "
     "uhinduye pad, na buri uko ugiye mu bwiherero. Mu kwoga, hera imbere "
     "ujyana inyuma kugirango wirinde infection."),
    ("puberty", "Uko witwara mu gihe k'imihango", _U_MEN,
     "Ni ingirakamaro ko abakobwa bagira ahantu hiherereye bakwisukurira mu "
     "gihe k'imihango. Kujya mu mihango ntibikwiye kukubuza gukora ibikorwa "
     "wari usanzwe ukora. Zimwe mu nama zagufasha: Koresha ubwiherero bufite "
     "inzugi zifungwa ndetse bunafite pubeli. Ubwiherero bukwiye kuba bufite "
     "amazi meza yo gukaraba ndetse n'isabune, bishobora kuba robine cyangwa "
     "ibaze irimo amazi. Jya ugendana Pad buri gihe kuko ushobora kujya mu "
     "mihango bitunguranye, cyangwa ukaba wava hagati mu kwezi kwawe."),
    ("puberty", "Ibibazo Biterwa n'Imihango — ku mubiri no ku marangamutima", _U_MEN,
     "Ku mubiri: Imihango igira ingaruka zitandukanye ku bakobwa. Hari iziza "
     "imihango itaratangira n'iziza imihango igitangira. Harimo: Kubabara mu "
     "nda, Kubabara umutwe, Kubabara umugongo, Kubabara amabere, Kubyimba inda, "
     "Kugira isesemi. Ku marangamutima: Abakobwa bashobora kugira "
     "amarangamutima y'ubwoko butandukanye bitewe n'ihindagurika ry'imisemburo "
     "mu mibiri yabo. Ibi bishobora gutangira habura iminsi mike ngo imihango "
     "ize hanyuma bikanakomeza mu minsi ya mbere y'imihango. Harimo: Guhindura "
     "amarangamutima bitunguranye, Kugira umushiha, Umujinya, Akababaro no "
     "kurira, Guhangayika."),
    ("puberty", "Uko wakwitwara mu bubabare butewe n'imihango", _U_MEN,
     "Kugira ngo ugabanye kubabara mu gihe uri mu mihango, nywa amazi menshi, "
     "urye ibiryo birimo intungamubiri zihagije harimo imboga, ibishyimbo "
     "n'imbuto. Kora imikino ngororamubiri cyangwa se unatembere n'amaguru. Mu "
     "gihe ububabare ari bwinshi mu gihe k'imihango, wafata imiti igabanya "
     "ububabare nka Paracetamol cyangwa Ibuprofen. Koga amazi ashyushye cyangwa "
     "gufata icupa ririmo amazi ashyushye ugashyira ku nda na byo bishobora "
     "gufasha kukugabanyiriza ububabare."),
    # — Ihohoterwa rishingiye ku gitsina (GBV -> gbv_consent) —
    ("gbv_consent", "Ihohoterwa rishingiye ku gitsina — icyo ari cyo", _U_GBV,
     "Ihohoterwa rishingiye ku gitsina ni ihohoterwa rikorerwa umuntu kubera "
     "igitsina cye cyangwa igitsina yahawe. Ihohoterwa rishingiye ku gitsina "
     "rishobora kubera ku ishuri, mu rugo cyangwa n'ahandi hantu ku mugaragaro "
     "cyangwa hihishe. Ihohoterwa rishingiye ku gitsina rishobora kuba ku "
     "mukobwa cyangwa se ku muhungu, ku mugabo cyangwa se ku mugore, gusa ku "
     "isi hose, rikunze kuba ku bakobwa n'abagore cyane cyane."),
    ("gbv_consent", "Ubwoko bw'ihohoterwa rishingiye ku gitsina", _U_GBV,
     "Irijyanye n'imibonano mpuzabitsina: Ihohoterwa rijyanye n'imibonano "
     "mpuzabitsina ni uguhatirwa gukora ibikorwa byose bijyanye n'imibonano "
     "mpuzabitsina utabishaka, utabyemeye. Ingero harimo kurongorwa mu gitsina, "
     "mu kibuno, mu kanwa, kubwirwa amagambo aganisha ku mibonano mpuzabitsina, "
     "gukorakora, gushimutwa ukajyanwa gukoreshwa imibonano mpuzabitsina. Ku "
     "Mubiri: Ihohoterwa rikorewe ku mubiri ni ibikorwa byose bibabaza umubiri "
     "cyangwa rigatera ibikomere ku mubiri. Ingero zirimo: Gukubita, gutwika, "
     "gutera umugeri, gukubita inshyi, gukubita ingumi, no kwica. Mu mutwe/mu "
     "ntekerezo: Ihohoterwa rikorerwa intekerezo ni ibikorwa byose byahungabanya "
     "intekerezo. Ingero zirimo: guserereza, gutukana, guhoza umuntu ku gitutu, "
     "guharabika. Ubukungu: Ihohoterwa ku bukungu ni ubugizi bwa nabi bwose "
     "bushobora kwangiza imibereho y'umuntu. Urugero nko gutwara umuntu "
     "umushahara we, kwangira umuntu gukora, kubuza umuntu gukoresha umutungo "
     "we."),
    ("gbv_consent", "Ihohoterwa ryo mu ngo", _U_GBV,
     "Ihohoterwa ryo mu ngo ni uburyo ubwo aribwo bwose bw'ihohoterwa bubaye "
     "hagati y'abantu babiri bakora imibonano mpuzabitsina cyangwa bakundana, "
     "baba barashakanye byemewe n'amategeko cyangwa batarashakanye. Ubu nibwo "
     "bwoko bw'ihohoterwa rishingiye ku gitsina bukunze kuba cyane. bukunze no "
     "kwitwa ihohoterwa rikozwe n'uwo mukundana, kandi rishobora kuba ku "
     "mibonano mpuzabitsina, ku mubiri cyangwa ku bukungu/imitungo."),
    ("gbv_consent", "Ihohoterwa — uko watwara amarangamutima", _U_GBV,
     "Nk'umuntu wahuye n'ihohoterwa rishingiye ku gitsina, ushobora kumva ufite "
     "ipfunwe, ufite ubwoba, kandi uri wenyine. Dore uko wakwitwara mu gihe "
     "wiyumva gutya: Ganira ku byakubayeho, ushake inshuti wabwira uko wiyumva, "
     "uwo mu muryango cyangwa umujyanama w'ubuzima. Iga gukora imirimo "
     "ngororamubiri igufasha koroshya amarangamutima yawe. Urugero nko kwiruka. "
     "Gerageza gukora ibyo ukunda. Urugero, kumva indirimbo cyangwa se "
     "gushushanya."),
    ("gbv_consent", "Ihohoterwa — shaka ahari umutekano", _U_GBV,
     "Ni ingenzi cyane gushaka ahantu hari umutekano wahungira ihohoterwa uri "
     "gukorerwa. Ababyeyi, abarimu, abakozi bo ku kigo cy'urubyiruko cyangwa "
     "Polisi bashobora kugufasha kubona ahantu hari umutekano waba uri muri iki "
     "gihe. Isange One Stop Centers receive victims of GBV and provide "
     "comprehensive care including medical, psychosocial, police and legal "
     "advice. They also provide emergency accommodation when needed. These "
     "centers are based in all district hospitals. Ganiriza umuntu wizeye: "
     "Kugira uwo uganiriza mu gihe wahungabanye bishobora kugufasha kwakira "
     "ibyabaye. Ku ishuri, ushobora kubiganiriza inshuti yawe magara cyangwa "
     "umwalimu wizeye. Mu rugo, ushobora kubiganiriza ababyeyi bawe, uwo "
     "muvukana, nyogosenge cyangwa se nyokorome."),
    # Emergency contact numbers — confirmed accurate; preserved exactly.
    ("gbv_consent", "Ihohoterwa — imirongo y'ubufasha itishyuzwa", _U_GBV,
     "Ifashishe serivise zabugenewe zikuri hafi: Ushobora kujya kwa muganga "
     "cyangwa ukajya kuri station ya polisi ikwegereye bakaguha ubufasha. Niba "
     "utabasha kujya hamwe muri aha, ushobora guhamagara imirongo itishyuzwa "
     "bakagufasha. Hamagara 116 utange amakuru ku ihohoterwa rikorerwa abana. "
     "Hamagara 3512 utange amakuru ku ihohoterwa rishingiye ku gitsina. "
     "Hamagara 3029 uvugane na Isange One Stop Center. Hamagara 8015 mu gihe "
     "ubonye ugiye kwiyahura cyangwa undi ufite ikibazo cyo mu mutwe uri mu "
     "bibazo."),
    ("gbv_consent", "Ihohoterwa — uko wafasha abandi", _U_GBV,
     "Niba ufite inshuti cyangwa umuntu wo mu muryango wawe wahuye n'ihohoterwa "
     "rishingiye ku gitsina, ushobora kumufasha muri ibyo bihe biba bitoroshye. "
     "Ushobora kumutega amatwi mu gihe ashaka kukuganiriza uko byamugendekeye, "
     "ushobora kumuherekeza kwa muganga kugirango bamufashe cyangwa se kuri "
     "polisi mu gihe yumva yiteguye kurega uwabimukoreye. Ntumushyireho "
     "igitutu cyo gukora ikintu atiteguye gukora, kandi ntugire na kimwe "
     "umushinja cyangwa ngo umucire urubanza."),
    ("gbv_consent", "Itandukaniro riri hagati y'ihohoterwa rishingiye ku gitsina no gufatwa ku ngufu", _U_GBV,
     "Ihohoterwa rishingiye ku gitsina ni ugukorerwa ibikorwa bishingiye ku "
     "mibonano mpuzabitsina utabyemeye. Ibi bikorwa birimo ibigera ku mubiri, "
     "ibinyuze mu magambo cyangwa ibitanyuze mu magambo. Bishobora no kubera "
     "kuri murandasi. Ingero zirimo: Kugukoraho utabishaka, Kwitegereza cyane "
     "mu buryo buganisha ku bice by'ibanga, Ibiganiro biganisha ku mibonano "
     "mpuzabitsina, Koherereza ubutumwa kuri murandasi. Gufatwa ku ngufu ni "
     "uburyo bwose bujyanye no gukora ku myanya y'ibanga y'umubiri w'umuntu "
     "atabyemeye. Ingero zirimo: Gukoresha imibonano mpuzabitsina ku gahato, "
     "Gusoma umuntu ku ngufu, Gukorakora ku gitsina cy'undi ku ngufu. Mu gihe "
     "wahuye n'ihohoterwa rishingiye ku gitsina cyangwa se wafashwe ku ngufu, "
     "amakosa si ayawe, nturi wenyine, turi hano kugirango tugufashe."),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provenance() -> dict:
    """Staging/provenance flags — identical to scripts.dev_seed_vector_store."""
    return {
        "approved": False,
        "review_status": "auto_test_unapproved",
        "requires_clinical_review": True,
    }


def build_chunks() -> list[dict]:
    """Build the RW chunk dicts (per Q&A pair / per section) with metadata.

    Idempotency: chunk id is the sha-256 of the cleaned text (same scheme as
    ``ingest_chunks``). Exact-duplicate texts collapse to one id automatically;
    the one near-duplicate Q&A pair called out in the task is already omitted
    from ``DOC_A`` above.
    """
    now = _now()
    chunks: list[dict] = []

    for i, (topic, question, answer) in enumerate(DOC_A):
        text = clean_text(f"{question}\n{answer}")
        # NB: no source_url key here — Doc A has no URL, and Pinecone rejects a
        # null metadata value (it must be absent, not None).
        chunks.append({
            "id": _hash(text),
            "text": text,
            "metadata": {
                "source": DOC_A_SOURCE,
                "title": question,
                "topic": topic,
                "language": "rw",
                "chunk_id": f"{DOC_A_SOURCE}:qa:{i}",
                "date_ingested": now,
                **_provenance(),
            },
        })

    for i, (topic, title, url, text) in enumerate(DOC_B):
        clean = clean_text(text)
        chunks.append({
            "id": _hash(clean),
            "text": clean,
            "metadata": {
                "source": DOC_B_SOURCE,
                "source_url": url,
                "title": title,
                "topic": topic,
                "language": "rw",
                "chunk_id": f"{DOC_B_SOURCE}:sec:{i}",
                "date_ingested": now,
                **_provenance(),
            },
        })
    return chunks


def _summarise(chunks: list[dict]) -> None:
    from collections import Counter
    by_source: Counter = Counter(c["metadata"]["source"] for c in chunks)
    by_topic: Counter = Counter(c["metadata"]["topic"] for c in chunks)
    by_lang: Counter = Counter(c["metadata"]["language"] for c in chunks)
    ids = [c["id"] for c in chunks]
    print("  chunks total          :", len(chunks))
    print("  unique ids            :", len(set(ids)), "(exact-dup collisions:",
          len(ids) - len(set(ids)), ")")
    print("  per source            :", dict(by_source))
    print("  per topic             :", dict(by_topic))
    print("  per language          :", dict(by_lang))


def _smoke(db) -> None:
    """RW retrieval smoke test: relevant queries must surface real chunks."""
    from app.ml.embeddings import retrieve_context
    queries = [
        ("Ubugimbi ni iki?", "puberty"),
        ("Imihango ni iki?", "puberty"),
        ("Uburyo bwo kwirinda gusama ni ubuhe?", "contraception"),
        ("Ihohoterwa rishingiye ku gitsina ni iki?", "gbv_consent"),
    ]
    print("\nKinyarwanda retrieval smoke test (lang=rw):")
    ok = True
    for q, topic in queries:
        hits = retrieve_context(q, "rw", top_k=3, topic=topic)
        mark = "OK " if hits else "!! "
        ok = ok and bool(hits)
        top = f"{hits[0]['score']:.3f} {str(hits[0].get('title'))[:48]!r}" if hits else "(0 results)"
        print(f"  {mark}[{topic:12}] {q!r} -> {len(hits)} hit(s); top={top}")
    print("SMOKE:", "PASS" if ok else "FAIL — some RW queries returned 0 chunks")


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest the two Kinyarwanda SRH docs.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Chunk + print counts only; no embedding or upsert.")
    ap.add_argument("--smoke", action="store_true",
                    help="After ingest, run the RW retrieval smoke test.")
    args = ap.parse_args()

    chunks = build_chunks()
    print("=" * 64)
    print("KINYARWANDA KB INGESTION — chunk build")
    print("=" * 64)
    _summarise(chunks)

    if args.dry_run:
        print("\ndry-run: nothing embedded or upserted.")
        return

    # Ensure the KnowledgeEntry table exists (dev convenience for sqlite).
    from app.database import Base, SessionLocal, engine
    from app import models  # noqa: F401  register tables
    from app.services.ingestion import ingest_chunks
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Ingest each document separately so the JSONL cache + report stay
        # per-document (ingest_chunks caches under the batch's first source).
        doc_a = [c for c in chunks if c["metadata"]["source"] == DOC_A_SOURCE]
        doc_b = [c for c in chunks if c["metadata"]["source"] == DOC_B_SOURCE]
        rep_a = ingest_chunks(doc_a, db)
        rep_b = ingest_chunks(doc_b, db)
        print("\nINGESTION REPORT")
        print(f"  Document A ({DOC_A_SOURCE}): ingested={rep_a['ingested']} "
              f"skipped={rep_a['skipped']} per_topic={rep_a['per_topic']}")
        print(f"  Document B ({DOC_B_SOURCE}): ingested={rep_b['ingested']} "
              f"skipped={rep_b['skipped']} per_topic={rep_b['per_topic']}")
        if args.smoke:
            _smoke(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
