"""
download_knesset.py  —  Download Knesset committee protocols and extract
agency-representative speech segments for GovPersona knowledge bases.

HOW IT WORKS:
  1. Queries the Knesset OData API for protocol documents from target committees
  2. Downloads each .doc file (which is actually docx format)
  3. Parses speaker-tagged segments: << דובר >> Name (Org): << דובר >>
  4. Matches speakers/attendees to our 6 agencies
  5. Saves extracted speech as text chunks in knowledge_base/<org>/knesset/

RUN:
  python download_knesset.py

After running, ingest with:
  python ingest.py --org finance_ministry
  python ingest.py --org central_bank
  ... etc, then python export_kb.py
"""

import sys
import io
import time
import re
import requests
from pathlib import Path
from docx import Document

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE    = Path(__file__).parent
KB      = BASE / "knowledge_base"
CACHE   = BASE / "knesset_cache"          # raw .doc downloads
CACHE.mkdir(exist_ok=True)

ODATA   = "https://knesset.gov.il/Odata/ParliamentInfo.svc"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GovPersona/1.0)"}

# =============================================================================
# Target committees  (Knesset 24 + 25)
# Finance, Economic Affairs, Constitution/Justice, Labor/Welfare
# =============================================================================
TARGET_COMMITTEES = {
    # Knesset 25
    4186: ("K25", "Finance Committee"),
    4191: ("K25", "Constitution, Law & Justice"),
    4193: ("K25", "Economic Affairs"),
    4196: ("K25", "Labor & Welfare"),
    # Knesset 24
    2216: ("K24", "Finance Committee"),
    2220: ("K24", "Constitution, Law & Justice"),
    2222: ("K24", "Economic Affairs"),
    2217: ("K24", "Labor & Welfare"),
}

# =============================================================================
# Agency keyword matching
# Each agency has a list of Hebrew keyword patterns found in:
#   - the attendees section (org affiliation after dash)
#   - speaker attribution lines
# =============================================================================
AGENCY_KEYWORDS = {
    "finance_ministry": [
        "משרד האוצר", "האוצר", "מנכ\"ל האוצר", "שר האוצר",
        "סגן שר האוצר", "חשב כללי", "מנהל תקציבים",
        "אגף התקציבים", "החשב הכללי", "כלכלן ראשי",
        "משרד אוצר",
    ],
    "central_bank": [
        "בנק ישראל", "נגיד", "המפקח על הבנקים",
        "בנק המרכזי", "המחלקה המוניטרית",
        "הפיקוח על הבנקים", "בנק-ישראל",
        "מפקח על הבנקים",
    ],
    "securities_authority": [
        "רשות ניירות ערך", "רשות לניירות ערך",
        "רשות לני\"ע", "ני\"ע", "ניי\"ע",
        "יו\"ר רשות ניירות", "יושבת-ראש רשות ניירות",
        "יושב-ראש רשות ניירות", "מנכ\"ל רשות ניירות",
        "רנ\"ע",
    ],
    "capital_markets_authority": [
        "רשות שוק ההון", "שוק ההון ביטוח וחיסכון",
        "הממונה על שוק ההון", "הממונה על הביטוח",
        "רשות שוה\"ב", "שוה\"ב",
        "ביטוח וחיסכון", "שוק ההון, ביטוח",
        "הממונה על רשות שוק",
    ],
    "ministry_of_justice": [
        "משרד המשפטים", "היועץ המשפטי לממשלה",
        "פרקליטות המדינה", "סנגוריה הציבורית",
        "רשם החברות", "רשות האכיפה והגבייה",
        "פרקליטות", "היועמ\"ש",
        "משרד משפטים",
    ],
    "tax_authority": [
        "רשות המסים", "מנהל רשות המסים",
        "אגף המכס", "נציב מס הכנסה",
        "רמ\"ה", "מינהל מס הכנסה",
        "פקיד שומה", "רשות המיסים",
        "מיסוי מקרקעין",
    ],
}

def org_for_text(text):
    """Return list of org IDs whose keywords appear in the text."""
    orgs = []
    for org, kws in AGENCY_KEYWORDS.items():
        if any(kw in text for kw in kws):
            orgs.append(org)
    return orgs

# =============================================================================
# Knesset API helpers
# =============================================================================
def api_get(path, params=None):
    url = f"{ODATA}/{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

def get_protocol_sessions(committee_id):
    """Return list of (CommitteeSessionID, StartDate, FilePath) for protocols."""
    results = []
    skip = 0
    page = 200
    while True:
        data = api_get("KNS_DocumentCommitteeSession", {
            "$format": "json",
            "$filter": "GroupTypeID eq 23",
            "$select": "CommitteeSessionID,FilePath",
            "$top": page,
            "$skip": skip,
        })
        values = data.get("value", [])
        if not values:
            break
        results.extend(values)
        if len(values) < page:
            break
        skip += page
    return results


def get_sessions_for_committee(committee_id):
    """Return list of (CommitteeSessionID, StartDate) for a committee."""
    results = []
    skip = 0
    page = 100
    while True:
        data = api_get("KNS_CommitteeSession", {
            "$format": "json",
            "$filter": f"CommitteeID eq {committee_id}",
            "$select": "CommitteeSessionID,StartDate",
            "$top": page,
            "$skip": skip,
        })
        values = data.get("value", [])
        if not values:
            break
        results.extend(values)
        if len(values) < page:
            break
        skip += page
    return results


def get_protocol_docs_for_sessions(session_ids):
    """Given a set of session IDs, return (session_id -> FilePath) for protocol docs.
    Uses batches of 10 to keep URLs short (50-batch caused 404 on Knesset API)."""
    result = {}
    ids_list = list(session_ids)
    batch = 10
    for i in range(0, len(ids_list), batch):
        chunk = ids_list[i:i+batch]
        id_filter = " or ".join(f"CommitteeSessionID eq {sid}" for sid in chunk)
        try:
            data = api_get("KNS_DocumentCommitteeSession", {
                "$format": "json",
                "$filter": f"GroupTypeID eq 23 and ({id_filter})",
                "$select": "CommitteeSessionID,FilePath",
            })
            for v in data.get("value", []):
                if v.get("FilePath"):
                    result[v["CommitteeSessionID"]] = v["FilePath"]
        except Exception as e:
            print(f"    Warning: batch query failed: {e}")
        time.sleep(0.2)
    return result

# =============================================================================
# Protocol parsing
# =============================================================================
# Matches all speaker role types: דובר (speaker), יור (chair), מציג (presenter),
# נציג (representative), רפרנט (referent), מגיב (respondent), מנהל (director)
SPEAKER_RE = re.compile(
    r'<<\s*(דובר|דובר_המשך|יור|מציג|נציג|רפרנט|מגיב|מנהל|אורח)\s*>>\s*(.+?):\s*<<'
)

# Section headers that introduce attendee lists
ATTENDEE_HEADERS = re.compile(
    r'^(מוזמנים|נוכחים|הוזמנו|משתתפים|נכחו|נציגי הממשלה|נציגי רשויות|אורחים)\s*:?\s*$'
)
# Separator between name and role in attendee lines  (– or - or ,)
ATTENDEE_SEP = re.compile(r'\s*[–\-,]\s*')


def build_name_org_map(paragraphs):
    """
    Parse the attendee sections of a protocol and return {first_word_of_name: [org_ids]}.
    This lets us identify speakers by name even when their org isn't in the speaker line.
    """
    name_map = {}
    in_attendee = False
    for para in paragraphs:
        if ATTENDEE_HEADERS.match(para):
            in_attendee = True
            continue
        # Attendee sections end when we hit a << tag or a blank-ish structural line
        if '<<' in para or (in_attendee and len(para) > 120):
            in_attendee = False
            continue
        if not in_attendee or not para:
            continue
        # Each attendee line: "Name Name – Title/Org" or "Name, Org"
        parts = ATTENDEE_SEP.split(para, maxsplit=1)
        if len(parts) == 2:
            name_part, role_part = parts[0].strip(), parts[1].strip()
            orgs = org_for_text(role_part)
            if orgs and name_part:
                # Key on first word of name (most distinctive)
                first = name_part.split()[0]
                for org in orgs:
                    name_map.setdefault(first, set()).add(org)
    return {k: list(v) for k, v in name_map.items()}


def speaker_orgs(raw_speaker, name_map):
    """
    Return org IDs for a speaker attribution string, checking both
    the full text and the attendee name map.
    """
    orgs = set(org_for_text(raw_speaker))
    # Check first word of speaker name against attendee map
    first_word = raw_speaker.split()[0] if raw_speaker else ""
    if first_word in name_map:
        orgs.update(name_map[first_word])
    return list(orgs)


def parse_protocol(path, committee_name, session_date, session_id):
    """
    Parse a protocol docx file.
    Returns list of dicts:
      {org, speaker, text, source, committee, date, session_id}
    """
    try:
        doc = Document(str(path))
    except Exception:
        return []

    paragraphs = [p.text.strip() for p in doc.paragraphs]
    full_text  = "\n".join(paragraphs)

    # Quick check: does this protocol mention any of our agencies at all?
    relevant_orgs = org_for_text(full_text)
    if not relevant_orgs:
        return []

    # Build name→org map from attendee sections
    name_map = build_name_org_map(paragraphs)

    # Also build name→org map from << נושא >> topic lines which often name officials with their orgs
    # e.g. << נושא >> סקירת הממונה על שוק ההון, ד"ר משה ברקת << נושא >>
    TOPIC_RE = re.compile(r'<<\s*נושא\s*>>\s*(.+?)\s*<<')
    for para in paragraphs:
        tm = TOPIC_RE.search(para)
        if tm:
            topic_text = tm.group(1)
            topic_orgs = org_for_text(topic_text)
            if topic_orgs:
                # Extract name after comma or "," — usually "...שם הפקיד" at end
                # Common patterns: "סקירת ... , ד"ר שם שם" or "סקירת שם שם, יו"ר ..."
                for part in re.split(r'[,،]', topic_text):
                    part = part.strip()
                    # Remove titles like ד"ר, פרופ', מר, גב'
                    part = re.sub(r'^(ד"ר|פרופ\'|מר|גב\'|הד"ר)\s+', '', part).strip()
                    words = part.split()
                    if 2 <= len(words) <= 4:  # plausible name length
                        first = words[0]
                        for org in topic_orgs:
                            name_map.setdefault(first, set())
                            if isinstance(name_map[first], set):
                                name_map[first].add(org)
                            else:
                                name_map[first] = set(name_map[first]) | {org}
    # Also scan all non-speaker paragraphs for "Name, Title/Org" introduction patterns.
    # Example: chair says "ענת גואטה, יושבת-ראש הרשות לניירות ערך, הבמה לרשותך"
    # This links the name to the org even when the attendee list is sparse.
    INTRO_RE = re.compile(
        r'([\u05D0-\u05FA"\'\u05F0-\u05F4]{2,}(?:\s+[\u05D0-\u05FA"\'\u05F0-\u05F4]{2,}){1,3})'
        r'[,،]\s+'
        r'([^\n,،]{5,80})'
    )
    for para in paragraphs:
        if '<<' in para or len(para) < 10:
            continue
        for intro_m in INTRO_RE.finditer(para):
            name_cand = intro_m.group(1).strip()
            role_text  = intro_m.group(2).strip()
            intro_orgs = org_for_text(role_text)
            if intro_orgs:
                first = name_cand.split()[0]
                cur = name_map.get(first, set())
                if isinstance(cur, list):
                    cur = set(cur)
                for org in intro_orgs:
                    cur.add(org)
                name_map[first] = cur

    # Convert sets to lists
    name_map = {k: list(v) if isinstance(v, set) else v for k, v in name_map.items()}

    # Parse speaker blocks
    segments = []
    current_speaker = None
    current_speaker_orgs = []
    current_lines = []

    def flush():
        if current_speaker and current_lines and current_speaker_orgs:
            text = " ".join(current_lines).strip()
            if len(text) > 50:   # skip very short fragments
                for org in current_speaker_orgs:
                    segments.append({
                        "org":          org,
                        "speaker":      current_speaker,
                        "text":         text,
                        "source":       f"knesset_{session_id}_{committee_name}_{session_date}.txt",
                        "committee":    committee_name,
                        "date":         session_date,
                        "session_id":   session_id,
                    })

    for para in paragraphs:
        m = SPEAKER_RE.search(para)
        if m:
            flush()
            current_lines = []
            raw_speaker = m.group(2).strip()
            current_speaker = raw_speaker
            current_speaker_orgs = speaker_orgs(raw_speaker, name_map)
        else:
            if para:
                current_lines.append(para)

    flush()
    return segments

# =============================================================================
# Main
# =============================================================================
def get_all_protocol_docs(min_session_id=2100000):
    """
    Fetch ALL protocol documents for recent Knessets without a huge OR filter.
    Returns dict: session_id -> FilePath
    """
    result = {}
    skip = 0
    page = 100
    print("  Pre-loading all protocol URLs (one-time, may take ~2 min)...")
    while True:
        try:
            data = api_get("KNS_DocumentCommitteeSession", {
                "$format": "json",
                "$filter": f"GroupTypeID eq 23 and CommitteeSessionID gt {min_session_id}",
                "$select": "CommitteeSessionID,FilePath",
                "$top": page,
                "$skip": skip,
            })
        except Exception as e:
            print(f"    Warning at skip={skip}: {e}")
            break
        values = data.get("value", [])
        for v in values:
            if v.get("FilePath"):
                result[v["CommitteeSessionID"]] = v["FilePath"]
        if len(values) < page:
            break
        skip += page
        time.sleep(0.15)
    print(f"  Loaded {len(result):,} protocol URLs")
    return result


def main():
    all_segments = {org: [] for org in AGENCY_KEYWORDS}

    # Collect all target session IDs first
    all_session_map = {}   # session_id -> (date, committee_name)
    for committee_id, (knesset_label, committee_name) in TARGET_COMMITTEES.items():
        print(f"  Fetching sessions: {committee_name} ({knesset_label})...")
        sessions = get_sessions_for_committee(committee_id)
        for s in sessions:
            sid = s["CommitteeSessionID"]
            all_session_map[sid] = (s.get("StartDate", "")[:10], committee_name, committee_id)
        print(f"    {len(sessions)} sessions")

    print(f"\n  Total target sessions: {len(all_session_map)}")

    # Fetch protocol doc URLs only for our target sessions (batch of 10 to avoid 404)
    print("  Fetching protocol doc URLs for target sessions...")
    protocol_map = get_protocol_docs_for_sessions(set(all_session_map.keys()))
    print(f"  {len(protocol_map)} of {len(all_session_map)} sessions have protocol docs\n")

    for committee_id, (knesset_label, committee_name) in TARGET_COMMITTEES.items():
        print(f"\n{'='*60}")
        print(f"  {committee_name} ({knesset_label})")
        print(f"{'='*60}")

        # Filter to sessions for this committee
        this_sessions = {sid: all_session_map[sid]
                         for sid in all_session_map
                         if all_session_map[sid][2] == committee_id and sid in protocol_map}
        print(f"  {len(this_sessions)} sessions with protocols")

        # Download and parse each protocol
        ok = skipped = no_agency = 0
        for sid, (date_str, _cname, _cid) in this_sessions.items():
            file_path = protocol_map[sid]
            cache_key = f"{committee_id}_{sid}.doc"
            cache_path = CACHE / cache_key

            # Download if not cached
            if not cache_path.exists():
                try:
                    r = requests.get(file_path, headers=HEADERS, timeout=30)
                    if r.status_code == 200 and len(r.content) > 2000:
                        cache_path.write_bytes(r.content)
                    else:
                        continue
                except Exception:
                    continue
                time.sleep(0.25)

            # Parse
            segs = parse_protocol(cache_path, committee_name, date_str, sid)
            if segs:
                for seg in segs:
                    all_segments[seg["org"]].append(seg)
                ok += 1
            else:
                no_agency += 1

        print(f"  -> {ok} protocols with agency content, {no_agency} without")

    # Save extracted segments to knowledge_base/<org>/knesset/
    print(f"\n{'='*60}")
    print("  Saving extracted segments")
    print(f"{'='*60}")

    total = 0
    for org, segs in all_segments.items():
        if not segs:
            continue
        out_dir = KB / org / "knesset"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Group by committee+date and write one text file per session
        by_source = {}
        for seg in segs:
            by_source.setdefault(seg["source"], []).append(seg)

        for source, group in by_source.items():
            out_file = out_dir / source
            with open(out_file, "w", encoding="utf-8") as f:
                meta = group[0]
                f.write("Knesset Committee Protocol\n")
                f.write(f"Committee: {meta['committee']}\n")
                f.write(f"Date: {meta['date']}\n")
                f.write(f"Session ID: {meta['session_id']}\n")
                f.write(f"Agency: {org}\n\n")
                for seg in group:
                    f.write(f"[Speaker: {seg['speaker']}]\n")
                    f.write(seg["text"])
                    f.write("\n\n")
            total += 1

        print(f"  {org}: {len(segs)} speech segments, {len(by_source)} sessions -> {out_dir.name}/knesset/")

    print(f"\n  Total: {total} files written")
    print("\n  Next: run ingest for each org, then export_kb.py")
    for org in AGENCY_KEYWORDS:
        print(f"    python ingest.py --org {org}")
    print("    python export_kb.py")

if __name__ == "__main__":
    main()
