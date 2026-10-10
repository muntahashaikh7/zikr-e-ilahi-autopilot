#!/usr/bin/env python3
"""
SEO automation module for the autopilot Islamic reminders track.

Input : one hadith entry dict from hadith_bank.json
        {id, topic, book, number, grade, arabic, urdu_tarjuma}
Output: dict with viral title (<=100 chars), keyword-rich description
        (with cross-platform links), tags (12-15), hashtags (5-8).

Template-based: works fully with NO API key.
enhance_with_gemini() is a clearly-marked stub where a future Gemini
call can upgrade the copy.
"""

import hashlib
import json
import re

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOOK_NAMES = {
    "bukhari": "Sahih Bukhari",
    "muslim": "Sahih Muslim",
    "tirmidhi": "Jami Tirmidhi",
    "abudawud": "Sunan Abu Dawud",
}

GRADE_NAMES = {
    "sahih": "Sahih",
    "hasan": "Hasan",
}

# Cross-platform links (standing cross-linking rule: every description
# must prominently link the other Zikr-e-Ilahi platforms).
PLATFORM_LINKS = {
    "YouTube": "https://www.youtube.com/@officialzikreilahi",
    "Instagram": "https://www.instagram.com/officialzikreilahi",
    "Facebook": "https://www.facebook.com/officialzikreilahi",
    "TikTok": "https://www.tiktok.com/@officialzikreilahi",
}

# Topic -> viral hook variants for titles (hook-first, Urdu+English mix).
# Variants rotate deterministically by entry id so daily videos vary.
TOPIC_HOOKS = {
    "dhikr": [
        "100 Martaba Ye Parho, Gunah Maaf!",
        "Ye Zikr Roz Parho — Beshumar Sawab",
        "SubhanAllah Ki Fazilat Janiye",
    ],
    "akhirah": [
        "Duniya Musafir Khana Hai!",
        "Aakhirat Ki Tayyari Karo",
        "Maut Ko Yaad Rakho",
    ],
    "salah": [
        "Namaz Chhoro Mat!",
        "Namaz Deen Ka Satoon Hai",
        "Namaz Ki Pabandi Karo",
    ],
    "dua": [
        "Dua Hi Ibadat Hai!",
        "Allah Se Mango, Wo Deta Hai",
        "Dua Ki Taqat Janiye",
    ],
    "sabr": [
        "Sabr Ka Sila Jannat Hai",
        "Mushkil Mein Sabr Karo",
        "Sabr Eeman Ka Hissa Hai",
    ],
    "tawba": [
        "Tauba Ka Darwaza Khula Hai",
        "Gunahon Se Tauba Karo",
        "Allah Tauba Qubool Karta Hai",
    ],
    "shukr": [
        "Shukar Ada Karo, Nemat Barhegi",
        "Allah Ka Shukar Ada Karna Seekho",
    ],
    "ilm": [
        "Deeni Ilm Hasil Karo",
        "Ilm Ki Fazilat Janiye",
    ],
    "iman": [
        "Eeman Ki Pehchan",
        "Momin Kaise Bano",
    ],
    "niyyah": [
        "Har Amal Niyyat Par Hai",
        "Niyyat Ka Sawab",
    ],
    "akhlaq": [
        "Achay Akhlaq Ki Fazilat",
        "Momin Ka Akhlaq Kaisa Ho",
        "Narmi Ikhtiyar Karo",
    ],
}

# Topic -> 2 engaging fazilat lines for the description.
TOPIC_FAZILAT = {
    "dhikr": (
        "Zikr-e-Ilahi dilon ka sukoon hai. Rozana chand minute ka zikr "
        "gunahon ki maafi aur beshumar sawab ka zariya banta hai."
    ),
    "akhirah": (
        "Duniya aarzi hai, aakhirat hamesha ki hai. Jo aakhirat ki tayyari "
        "karta hai, wahi kamyab hai."
    ),
    "salah": (
        "Namaz momin ki mairaj hai aur deen ka satoon. Namaz ki pabandi "
        "duniya o aakhirat dono mein kamyabi deti hai."
    ),
    "dua": (
        "Dua momin ka hathyar hai. Allah se mangna ibadat hai aur wo apne "
        "bandon ki dua zaroor sunta hai."
    ),
    "sabr": (
        "Sabr mushkil waqt mein momin ki pehchan hai. Sabr karne walon ke "
        "liye Allah ke paas be-hisab ajar hai."
    ),
    "tawba": (
        "Tauba ka darwaza maut tak khula hai. Sache dil se tauba karne wale "
        "ke gunah Allah maaf farma deta hai."
    ),
    "shukr": (
        "Shukar ada karne se nematein barhti hain. Jo Allah ka shukar ada "
        "karta hai, Allah usay aur ata karta hai."
    ),
    "ilm": (
        "Deeni ilm hasil karna har Musalman par farz hai. Ilm insan ko "
        "gumrahi se nikal kar hidayat ki taraf le jata hai."
    ),
    "iman": (
        "Eeman sab se qeemti daulat hai. Ise mazboot rakhna har momin ki "
        "zimmedari hai."
    ),
    "niyyah": (
        "Aamal ka daromadar niyyat par hai. Nek niyyat chhotay amal ko bhi "
        "bara sawab bana deti hai."
    ),
    "akhlaq": (
        "Achay akhlaq momin ki zeenat hain. Narm lehja aur husn-e-sulook "
        "logon ke dil jeet lete hain."
    ),
}

# ---------------------------------------------------------------------------
# Per-entry SEO overrides (2026-10-10): topic-level hooks/fazilat don't always
# match the specific matn — e.g. dua-003 is the "dua behind the brother's
# back" hadith (Muslim 2733), NOT the "dua hi ibadat hai" hadith (Tirmidhi
# 3372), so the topic hook "Dua Hi Ibadat Hai!" would be a wrong title.
# Entry-level accuracy always wins over topic defaults.
# ---------------------------------------------------------------------------
ENTRY_SEO_HOOK = {
    "dua-003": "Bhai Ke Liye Dua — Farishta Kehta Hai Aameen!",
}
ENTRY_SEO_FAZILAT = {
    "dua-003": (
        "Apne bhai ke liye peeth peeche ki gayi dua qabool hoti hai — "
        "farishta kehta hai: Aameen, aur tumhare liye bhi usi jaisa."
    ),
    "akhlaq-002": (
        "Parosi ko takleef na do, mehmaan ki izzat karo, bhalai ki baat "
        "kaho ya khamosh raho — yehi momin ka akhlaq hai."
    ),
}
# Full accurate tarjuma for the description line (bank's urdu_tarjuma is
# shortened for these two entries).
ENTRY_SEO_TARJUMA = {
    "akhlaq-002": (
        "جو اللہ اور قیامت کے دن پر ایمان رکھتا ہے، وہ اپنے پڑوسی کو تکلیف نہ دے؛ "
        "جو اللہ اور قیامت کے دن پر ایمان رکھتا ہے، وہ اپنے مہمان کی عزت کرے؛ "
        "اور جو اللہ اور قیامت کے دن پر ایمان رکھتا ہے، وہ بھلائی کی بات کہے یا خاموش رہے۔"
    ),
    "dua-003": (
        "مسلمان کی اپنے بھائی کے لیے پیٹھ پیچھے کی ہوئی دعا قبول ہوتی ہے؛ "
        "اس کے سر کے پاس ایک فرشتہ مقرر ہے — جب وہ اپنے بھائی کے لیے بھلائی کی دعا "
        "کرتا ہے، تو وہ فرشتہ کہتا ہے: آمین، اور تیرے لیے بھی اسی جیسا ہو۔"
    ),
}

# Topic -> keyword tags (Urdu-transliteration + English mix).
TOPIC_TAGS = {
    "dhikr": ["subhanallah", "zikr ki fazilat", "dhikr benefits", "tasbih", "allah ka zikr"],
    "akhirah": ["aakhirat", "akhirat ki tayyari", "qiyamat", "maut ki yaad", "day of judgment"],
    "salah": ["namaz", "namaz ki fazilat", "salah", "namaz ki pabandi", "prayer in islam"],
    "dua": ["dua", "dua ki taqat", "dua ki fazilat", "mangna", "islamic dua"],
    "sabr": ["sabr", "sabar ki fazilat", "patience in islam", "mushkil mein sabr"],
    "tawba": ["tauba", "toba", "istighfar", "gunahon se tauba", "repentance in islam"],
    "shukr": ["shukar", "shukr ada karna", "gratitude in islam", "allah ka shukar"],
    "ilm": ["ilm", "deeni ilm", "ilm ki fazilat", "seeking knowledge islam"],
    "iman": ["iman", "emaan", "iman ki alamat", "faith in islam"],
    "niyyah": ["niyyat", "niyyah", "amal aur niyyat", "intention in islam"],
    "akhlaq": ["akhlaq", "achay ikhlaq", "husn e akhlaq", "islamic manners", "narmi"],
}

TOPIC_HASHTAGS = {
    "dhikr": ["#SubhanAllah", "#Zikr"],
    "akhirah": ["#Aakhirat", "#Qiyamat"],
    "salah": ["#Namaz", "#Salah"],
    "dua": ["#Dua", "#DuaKiTaqat"],
    "sabr": ["#Sabr", "#Patience"],
    "tawba": ["#Tauba", "#Istighfar"],
    "shukr": ["#Shukar", "#Gratitude"],
    "ilm": ["#Ilm", "#Knowledge"],
    "iman": ["#Iman", "#Faith"],
    "niyyah": ["#Niyyat", "#Intention"],
    "akhlaq": ["#Akhlaq", "#GoodManners"],
}

BASE_TAGS = [
    "islamic reminder",
    "hadith in urdu",
    "zikr e ilahi",
    "islamic shorts",
    "deen islam",
    "sunnah",
]

BASE_HASHTAGS = ["#IslamicReminder", "#Hadith", "#ZikrEIlahi", "#IslamicShorts"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _book_name(book: str) -> str:
    return BOOK_NAMES.get(book.lower(), book.title())


def _grade_name(grade: str) -> str:
    return GRADE_NAMES.get(grade.lower(), grade.title())


def _pick_variant(entry_id: str, variants: list) -> str:
    """Deterministic rotation so daily titles vary per entry."""
    h = int(hashlib.md5(entry_id.encode("utf-8")).hexdigest(), 16)
    return variants[h % len(variants)]


def _reference_line(entry: dict) -> str:
    return (
        f"Reference: {_book_name(entry['book'])}, "
        f"Hadith {entry['number']} ({_grade_name(entry['grade'])})"
    )


# ---------------------------------------------------------------------------
# Main generator (template-based, no API key needed)
# ---------------------------------------------------------------------------

def generate_seo(entry: dict) -> dict:
    """
    Build a full SEO package for one hadith bank entry.

    Returns dict: {title, description, tags, hashtags}
    """
    topic = entry.get("topic", "").lower()
    book_ref = f"{_book_name(entry['book'])} {entry['number']}"

    # --- Title: viral hook first, always book + number, <=100 chars ---
    # Entry-level hook wins (matn-accurate); otherwise rotate topic hooks.
    hook = ENTRY_SEO_HOOK.get(entry.get("id", "")) or _pick_variant(
        entry.get("id", ""),
        TOPIC_HOOKS.get(topic, ["Islamic Reminder"]),
    )
    title = f"{hook} | {book_ref}"
    if len(title) > 100:
        # Trim hook (never the reference) to respect the limit.
        keep = 100 - len(f" | {book_ref}")
        title = f"{hook[:keep].rstrip()} | {book_ref}"

    # --- Description ---
    # Entry-level fazilat/tarjuma win (matn-accurate); else topic defaults.
    fazilat = ENTRY_SEO_FAZILAT.get(entry.get("id", ""), "") or TOPIC_FAZILAT.get(topic, "")
    hashtags = generate_hashtags(entry)
    desc_tarjuma = ENTRY_SEO_TARJUMA.get(entry.get("id", ""), entry.get('urdu_tarjuma', '').strip())
    lines = [
        f"🌙 {hook}",
        "",
        fazilat,
        "",
        f"📖 Tarjuma: {desc_tarjuma}",
        "",
        f"📚 {_reference_line(entry)}",
        "",
        "🤲 Is video ko share karke sadqa-e-jariya mein hissa lein!",
        "",
        "🔗 Zikr-e-Ilahi ko follow karein:",
    ]
    for name, url in PLATFORM_LINKS.items():
        lines.append(f"{name}: {url}")
    lines += [
        "",
        " ".join(hashtags),
        "",
        "🤖 Note: Ye video AI ki madad se auto-generate ki gayi hai — Zikr-e-Ilahi.",
    ]
    description = "\n".join(lines)

    return {
        "title": title,
        "description": description,
        "tags": generate_tags(entry),
        "hashtags": hashtags,
    }


def generate_tags(entry: dict) -> list:
    """12-15 tags: Urdu-transliteration + English mix, topic + book derived."""
    topic = entry.get("topic", "").lower()
    tags = []
    tags += TOPIC_TAGS.get(topic, [topic])
    tags.append(_book_name(entry["book"]).lower())          # e.g. "sahih bukhari"
    tags.append(f"{_book_name(entry['book'])} {entry['number']}".lower())
    tags += BASE_TAGS
    # De-dupe, preserve order, cap at 15.
    seen, out = set(), []
    for t in tags:
        t = t.strip().lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:15]


def generate_hashtags(entry: dict) -> list:
    """5-8 hashtags for Shorts/Reels."""
    topic = entry.get("topic", "").lower()
    tags = []
    tags += TOPIC_HASHTAGS.get(topic, [])
    tags += BASE_HASHTAGS
    seen, out = set(), []
    for h in tags:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out[:8]


# ---------------------------------------------------------------------------
# Future enhancement stub (clearly marked)
# ---------------------------------------------------------------------------

def enhance_with_gemini(entry: dict, api_key: str | None = None) -> dict:
    """
    STUB — future enhancement hook.

    When a Gemini API key is available, this function may call the Gemini API
    to rewrite/upgrade the title, description hooks and tags produced by
    generate_seo() with more creative, viral copy.

    Without an api_key it returns the template-based package unchanged, so
    the module ALWAYS works offline.
    """
    package = generate_seo(entry)
    if not api_key:
        return package
    # TODO: implement Gemini call here, e.g.:
    #   prompt = build prompt from entry + package
    #   response = gemini.generate(prompt, api_key)
    #   merge AI copy into package with validation
    # For now: fall through to template output.
    return package


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def verify_package(entry: dict, package: dict) -> list:
    """Return a list of problem strings (empty = pass)."""
    problems = []
    title = package.get("title", "")
    desc = package.get("description", "")
    tags = package.get("tags", [])
    hashtags = package.get("hashtags", [])

    if not title:
        problems.append("empty title")
    if len(title) > 100:
        problems.append(f"title too long ({len(title)} chars)")
    # NOTE (2026-10-10): compare space-stripped so book keys like "abudawud"
    # match display names like "Sunan Abu Dawud" (was a false positive).
    title_nospace = title.lower().replace(" ", "")
    if entry["book"].lower() not in title_nospace or str(entry["number"]) not in title:
        problems.append("title missing book/number reference")
    if not desc:
        problems.append("empty description")
    for name, url in PLATFORM_LINKS.items():
        if url not in desc:
            problems.append(f"description missing {name} link")
    if entry["number"] not in desc or _book_name(entry["book"]) not in desc:
        problems.append("description missing hadith reference")
    if not entry.get("urdu_tarjuma", "") or entry["urdu_tarjuma"] not in desc:
        problems.append("description missing urdu tarjuma")
    if not (12 <= len(tags) <= 15):
        problems.append(f"tags count {len(tags)} not in 12-15")
    if not (5 <= len(hashtags) <= 8):
        problems.append(f"hashtags count {len(hashtags)} not in 5-8")
    if any(not t for t in tags) or any(not h for h in hashtags):
        problems.append("empty tag/hashtag entry")
    return problems


if __name__ == "__main__":
    import os

    bank_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "hadith_bank.json")
    with open(bank_path, encoding="utf-8") as f:
        bank = json.load(f)
    entries = bank["entries"]

    # 3 diverse test entries: different topics + different books.
    test_ids = ["akhirah-001", "dhikr-003", "sabr-001"]
    by_id = {e["id"]: e for e in entries}
    tests = []
    for tid in test_ids:
        if tid in by_id:
            tests.append(by_id[tid])
    # Fallback: first entry of 3 distinct topics if ids differ.
    if len(tests) < 3:
        seen_topics, tests = set(), []
        for e in entries:
            if e["topic"] not in seen_topics:
                seen_topics.add(e["topic"])
                tests.append(e)
            if len(tests) == 3:
                break

    samples = []
    all_ok = True
    for e in tests:
        pkg = generate_seo(e)
        problems = verify_package(e, pkg)
        status = "PASS" if not problems else f"FAIL: {problems}"
        if problems:
            all_ok = False
        print(f"[{e['id']}] {e['topic']} | {e['book']} {e['number']}")
        print(f"  title ({len(pkg['title'])}ch): {pkg['title']}")
        print(f"  tags: {len(pkg['tags'])}, hashtags: {len(pkg['hashtags'])}")
        print(f"  -> {status}")
        samples.append({"entry_id": e["id"], "entry": e, "seo": pkg})

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "seo_samples.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
    # Validate the file is parseable JSON.
    json.load(open(out_path, encoding="utf-8"))
    print(f"\nWrote {out_path} (valid JSON: True)")
    print("ALL TESTS PASSED" if all_ok else "SOME TESTS FAILED")
