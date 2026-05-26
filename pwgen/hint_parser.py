"""Parse plain-language hints into a raw constraint dict."""
from __future__ import annotations
import re


def parse_hints(hints: list[str]) -> dict:
    """Convert a list of natural-language hint strings into a constraint dict."""
    cfg: dict = {}

    for hint in hints:
        h = hint.lower().strip()

        # Length
        m = re.match(r'^(\d+)\s+char', h)
        if m:
            cfg["length"] = int(m.group(1))
            continue

        m = re.match(r'^(?:min(?:imum)?\s+)?(?:length\s+)?at\s+least\s+(\d+)', h)
        if m:
            cfg["min_length"] = int(m.group(1))
            continue

        m = re.match(r'^(?:max(?:imum)?\s+)?(?:length\s+)?(?:at\s+most|no\s+more\s+than)\s+(\d+)', h)
        if m:
            cfg["max_length"] = int(m.group(1))
            continue

        # No consecutive
        m = re.match(r'^no\s+(\d+)\s+(.+?)\s+in\s+a\s+row', h)
        if m:
            count = int(m.group(1))
            what = m.group(2).strip()
            char = "any"
            if what in ("zeros", "0s"):
                char = "0"
            elif what in ("ones", "1s"):
                char = "1"
            elif len(what) == 1:
                char = what
            nc = cfg.setdefault("no_consecutive", [])
            nc.append({"char": char, "count": count})
            continue

        # Max repeats
        m = re.match(r'^same\s+digit\s+not\s+more\s+than\s+(\d+)', h)
        if m:
            mr = cfg.setdefault("max_repeats", {})
            mr["digits"] = int(m.group(1))
            continue

        m = re.match(r'^(?:any\s+)?digit\s+(?:appears?\s+)?(?:at\s+most|no\s+more\s+than)\s+(\d+)', h)
        if m:
            mr = cfg.setdefault("max_repeats", {})
            mr["digits"] = int(m.group(1))
            continue

        # Require uppercase
        if re.search(r'must\s+have\s+upper|require\s+upper|needs?\s+upper', h):
            co = cfg.setdefault("charset_options", {})
            rc = co.setdefault("require_classes", [])
            if "upper" not in rc:
                rc.append("upper")
            continue

        # Require digit
        if re.search(r'must\s+have\s+digit|require\s+digit|needs?\s+(?:a\s+)?digit', h):
            co = cfg.setdefault("charset_options", {})
            rc = co.setdefault("require_classes", [])
            if "digit" not in rc:
                rc.append("digit")
            continue

        # No keyboard walks
        if re.search(r'no\s+keyboard\s+walk|avoid\s+keyboard\s+walk', h):
            cfg["keyboard_walk"] = {"reject_if_walk_ratio_above": 0.5}
            continue

        # Starts with
        m = re.match(r'^starts?\s+with\s+["\']?(\S+?)["\']?$', h)
        if m:
            patterns = cfg.setdefault("patterns", {})
            sw = patterns.setdefault("startswith", [])
            sw.append(m.group(1))
            continue

        # Ends with
        m = re.match(r'^ends?\s+with\s+["\']?(\S+?)["\']?$', h)
        if m:
            patterns = cfg.setdefault("patterns", {})
            ew = patterns.setdefault("endswith", [])
            ew.append(m.group(1))
            continue

        # Entropy
        m = re.match(r'^(?:at\s+least\s+)?(\d+(?:\.\d+)?)\s+bits?\s+entropy', h)
        if m:
            cfg["entropy"] = {"min_bits": float(m.group(1))}
            continue

        # Charset
        if re.search(r'\bdigits?\s+only\b|\bnumbers?\s+only\b', h):
            cfg["charset"] = "digits"
            continue
        if re.search(r'\bletters?\s+only\b|\balpha\s+only\b', h):
            cfg["charset"] = "alpha"
            continue
        if re.search(r'\balphanumeric\b', h):
            cfg["charset"] = "alnum"
            continue

    return cfg
