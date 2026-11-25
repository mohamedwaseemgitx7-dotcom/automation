"""Text normalisation: lower-case, fix common chat spellings, map Malay/Manglish words to English
so keyword search and the English embedding model both understand the question."""
import re
import unicodedata

# chat shorthand / typos -> English
SPELLING = {
    "wat": "what", "wht": "what", "whr": "where", "ur": "your", "u": "you", "r": "are", "pls": "please",
    "plz": "please", "thx": "thanks", "tq": "thanks", "ty": "thanks", "servis": "service", "sevice": "service",
    "lappy": "laptop", "lapto": "laptop", "laptp": "laptop", "compter": "computer", "comp": "computer",
    "repiar": "repair", "repare": "repair", "prise": "price", "prize": "price", "hw": "how", "hv": "have",
    "cn": "can", "nd": "need", "wan": "want", "wanna": "want", "dun": "do not", "cant": "cannot",
    "addr": "address", "adress": "address", "virous": "virus", "vairus": "virus", "upgarde": "upgrade",
    "opn": "open", "tmr": "tomorrow", "2day": "today", "hrs": "hours", "nite": "night", "ssd's": "ssd",
}

# Malay / Manglish -> English (word level)
MALAY = {
    "berapa": "how much", "harga": "price", "kos": "cost", "caj": "charge", "baiki": "repair", "repair": "repair",
    "rosak": "broken", "spoil": "broken", "perkhidmatan": "service", "servis": "service", "beli": "buy",
    "jual": "sell", "alamat": "address", "kedai": "shop", "pejabat": "office", "buka": "open", "tutup": "close",
    "waktu": "hours", "masa": "time", "hari": "day", "kawasan": "area", "datang": "come", "rumah": "home",
    "panas": "overheat", "lambat": "slow", "jaminan": "warranty", "percuma": "free", "segera": "urgent",
    "kecemasan": "emergency", "hubungi": "contact", "emel": "email", "telefon": "phone", "komputer": "computer",
    "naik": "upgrade", "taraf": "", "pasang": "install", "tak": "not", "tidak": "not", "boleh": "can",
    "ada": "have", "saya": "i", "nak": "want", "mahu": "want", "awak": "you", "anda": "you", "ke": "",
    "tak boleh on": "cannot turn on", "terima": "thanks", "kasih": "", "manusia": "human", "ejen": "agent",
    "staf": "staff", "bercakap": "talk", "dengan": "with", "skrin": "screen", "pecah": "broken",
}

# Tanglish (Tamil in English letters) -> English
TANGLISH = {
    "enga": "where", "engey": "where", "iruku": "is", "irukku": "is", "irukka": "is there", "iruka": "is there",
    "evlo": "how much", "evvalavu": "how much", "vilai": "price", "venum": "need", "vendum": "need",
    "unga": "your", "ungal": "your", "eppo": "when", "eppadi": "how", "enna": "what", "kedaikuma": "available",
    "pannuveengala": "do you", "pannunga": "please do", "sollunga": "tell", "seri": "ok", "nanri": "thanks",
    "kadai": "shop", "veedu": "home", "veetuku": "to home", "varuveengala": "will you come", "sari": "ok",
}
MALAY.update(TANGLISH)

MALAY_MARKERS = {"berapa", "harga", "baiki", "rosak", "boleh", "saya", "nak", "tak", "tidak", "ada", "kedai",
                 "alamat", "buka", "tutup", "waktu", "perkhidmatan", "terima", "kasih", "selamat", "apa",
                 "macam", "mana", "bila", "awak", "anda", "lah", "ke", "datang", "rumah", "percuma", "segera"}

_WORD = re.compile(r"[a-z0-9஀-௿']+")


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def tokens(text: str) -> list[str]:
    return _WORD.findall(clean(text).lower())


def to_english(text: str) -> str:
    out = []
    for w in tokens(text):
        w = SPELLING.get(w, w)
        w = MALAY.get(w, w)
        if w:
            out.append(w)
    return " ".join(out)
