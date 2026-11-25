"""Independent guardrail checks around the local LLM."""
import re

INJECTION = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|the\s+|your\s+|previous\s+|above\s+)*(instructions|rules|prompt)|"
    r"system prompt|you are now|act as|developer mode|jailbreak|reveal (your|the) (prompt|instructions)",
    re.I)
HUMAN = ("human", "agent", "real person", "talk to staff", "talk to someone", "speak to someone", "owner",
         "complain", "complaint", "manager", "manusia", "ejen", "aal kitta pesanum", "customer service")
GREETINGS = {"hi", "hello", "hey", "hai", "helo", "salam", "vanakkam", "good morning", "good evening",
             "selamat pagi", "assalamualaikum"}
HARMFUL = re.compile(r"\b(bomb|weapon|hack into|steal|password of|credit card number|kill)\b", re.I)

FACT = re.compile(
    r"(RM\s?\d[\d,.]*|\$\s?\d[\d,.]*|₹\s?\d[\d,.]*|\b\d[\d,.]*\s?(ringgit|rm|rupees?|%)\b|"   # money / percent
    r"\+?\d[\d\s-]{7,}\d|"                                                             # phone numbers
    r"[\w.+-]+@[\w-]+\.[\w.]+|"                                                         # emails
    r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b|\b\d{1,2}:\d{2}\b)", re.I)                         # times


def strip_injection(text: str) -> str:
    return INJECTION.sub("[removed]", text)


def wants_human(words_text: str) -> bool:
    t = f" {words_text.lower()} "
    return any(f" {h} " in t for h in HUMAN)


def is_greeting(words: list[str]) -> bool:
    j = " ".join(words)
    return len(words) <= 4 and any(g == j or j.startswith(g + " ") for g in GREETINGS)


def is_harmful(text: str) -> bool:
    return bool(HARMFUL.search(text))


def _norm_fact(f: str) -> str:
    return re.sub(r"[\s,.-]", "", f.lower()).replace("ringgit", "rm")


def unsupported_facts(answer: str, evidence: str) -> list[str]:
    """Facts (prices, phones, emails, times) in the answer that do not appear in the retrieved evidence."""
    ev = _norm_fact(evidence)
    bad = []
    for m in FACT.finditer(answer):
        f = m.group(0)
        if _norm_fact(f) not in ev:
            bad.append(f.strip())
    return bad


def trim_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    cut = " ".join(words[:max_words])
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > len(cut) // 2 else cut + "…"


EMOJI = re.compile("[🌀-🫿☀-➿️]")


def one_emoji(text: str) -> str:
    """Keep the first emoji only; staff chat, not a sticker wall."""
    seen = False

    def keep(m):
        nonlocal seen
        if m.group(0) == "️":
            return m.group(0) if not seen else ""
        if seen:
            return ""
        seen = True
        return m.group(0)
    return re.sub(r"[ 	]{2,}", " ", EMOJI.sub(keep, text)).strip()


NEGATION = re.compile(r"\b(?:we\s+)?(?:don't|do not|doesn't|does not|no longer|cannot|can't|won't)\s+"
                      r"(?:offer|provide|sell|do|repair|have|fix|support|cover|service)\b", re.I)


def unsupported_negation(answer: str, evidence: str) -> str | None:
    """A 'we don't offer X' claim the knowledge never states. Returns the phrase, or None."""
    a = answer.replace("’", "'").replace("‘", "'")
    ev = evidence.replace("’", "'").lower()
    for m in NEGATION.finditer(a):
        if m.group(0).lower() not in ev:
            return m.group(0)
    return None
