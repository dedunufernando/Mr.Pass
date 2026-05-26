"""
Generate the bundled small_10k.txt wordlist from common password patterns.
Run once: python scripts/gen_wordlist.py

Produces a ~10K line seed file covering the most common password patterns
without requiring an external download. For real-world use, replace with
rockyou or SecLists.
"""
from __future__ import annotations
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "wordlists", "small_10k.txt")

# ── Base vocabulary ──────────────────────────────────────────────────────────

NAMES = [
    "james", "john", "robert", "michael", "william", "david", "richard", "joseph",
    "thomas", "charles", "mary", "patricia", "linda", "barbara", "elizabeth",
    "jennifer", "maria", "susan", "margaret", "dorothy", "jessica", "sarah",
    "karen", "lisa", "nancy", "ashley", "daniel", "matthew", "anthony", "mark",
    "donald", "steven", "paul", "andrew", "joshua", "kevin", "brian", "george",
    "timothy", "ronald", "edward", "jason", "jeffrey", "ryan", "jacob", "gary",
    "nicholas", "eric", "jonathan", "stephen", "larry", "justin", "scott",
    "brandon", "benjamin", "samuel", "raymond", "gregory", "frank", "alexander",
    "patrick", "raymond", "jack", "dennis", "jerry",
]

WORDS = [
    "password", "welcome", "login", "admin", "access", "master", "secret",
    "dragon", "monkey", "shadow", "sunshine", "princess", "superman", "batman",
    "baseball", "football", "soccer", "hockey", "tennis", "letmein", "mustang",
    "hunter", "ranger", "harley", "dakota", "cookie", "cheese", "butter",
    "coffee", "winter", "summer", "spring", "autumn", "flower", "purple",
    "orange", "yellow", "silver", "golden", "thunder", "lightning", "freedom",
    "forever", "always", "never", "nothing", "everything", "whatever", "midnight",
    "sunrise", "sunset", "rainbow", "diamond", "crystal", "phoenix", "falcon",
    "eagle", "tiger", "lion", "wolf", "bear", "cobra", "viper", "panther",
    "matrix", "hacker", "cyber", "online", "mobile", "digital", "network",
    "computer", "internet", "system", "android", "iphone", "windows", "linux",
    "ubuntu", "google", "yahoo", "amazon", "apple", "microsoft", "facebook",
    "twitter", "instagram", "youtube", "netflix", "spotify", "github", "reddit",
    "chess", "poker", "gaming", "player", "gamer", "ninja", "pirate", "zombie",
    "killer", "warrior", "knight", "wizard", "magic", "sword", "shield",
    "rocket", "galaxy", "universe", "cosmos", "planet", "saturn", "jupiter",
    "mercury", "venus", "apollo", "hercules", "atlas", "titan", "zeus",
    "alpha", "beta", "gamma", "delta", "omega", "sigma", "theta", "lambda",
    "tequila", "corona", "whiskey", "vodka", "brandy", "mojito", "bourbon",
    "mustard", "pepper", "vanilla", "cherry", "mango", "banana", "lemon",
    "peach", "apple", "melon", "coconut", "pineapple", "avocado", "potato",
    "lovely", "pretty", "happy", "lucky", "crazy", "funky", "fancy", "shiny",
    "baby", "angel", "heart", "love", "star", "moon", "kiss", "rose",
]

NUMBERS = [str(n) for n in range(100)]
YEARS   = [str(y) for y in range(1970, 2026)]
SYMBOLS = ["!", "@", "#", "$", "*", "1"]

# ── Generation ───────────────────────────────────────────────────────────────

def gen() -> list[str]:
    seen: set[str] = set()
    out:  list[str] = []

    def add(w: str) -> None:
        if w not in seen and len(w) >= 4:
            seen.add(w)
            out.append(w)

    # Pure names and words
    for w in NAMES + WORDS:
        add(w)
        add(w.capitalize())
        add(w.upper())

    # Word + short number
    for w in NAMES + WORDS:
        for n in NUMBERS[:30]:
            add(w + n)
            add(w.capitalize() + n)

    # Word + year
    for w in (NAMES + WORDS)[:60]:
        for y in YEARS[-20:]:  # 2006-2025
            add(w + y)
            add(w.capitalize() + y)

    # Word + symbol
    for w in (NAMES + WORDS)[:40]:
        for s in SYMBOLS:
            add(w + s)
            add(w.capitalize() + s)
            for n in ["1", "12", "123"]:
                add(w + n + s)

    # Simple numeric sequences
    for length in range(4, 10):
        for start in range(10):
            add("".join(str((start + i) % 10) for i in range(length)))

    # Repeated patterns
    for c in "0123456789":
        for l in range(4, 9):
            add(c * l)

    # Common passwords not covered above
    extras = [
        "123456", "1234567", "12345678", "123456789", "1234567890",
        "000000", "111111", "222222", "333333", "444444", "555555",
        "666666", "777777", "888888", "999999",
        "123123", "456456", "789789", "121212", "131313",
        "abc123", "abc1234", "qwerty", "qwerty123", "qwerty1",
        "password1", "password123", "password!", "Password1",
        "iloveyou", "iloveyou1", "trustno1", "letmein1",
        "monkey1", "dragon1", "master1", "shadow1", "michael1",
        "passw0rd", "p@ssword", "p@ssw0rd", "P@ssw0rd",
        "admin123", "admin1", "root123", "test123", "user123",
        "welcome1", "welcome123", "hello123", "hello1",
        "sunshine1", "princess1", "baseball1", "football1",
    ]
    for e in extras:
        add(e)

    return out[:10000]


def main() -> None:
    words = gen()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("# pwgen small_10k wordlist — common password seeds\n")
        f.write("# For real-world use replace with rockyou / SecLists\n")
        for w in words:
            f.write(w + "\n")
    print(f"Written {len(words):,} words -> {OUT}")


if __name__ == "__main__":
    main()
