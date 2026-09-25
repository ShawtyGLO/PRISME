"""Outil : enveloppe dans U8 (...) tout littéral de chaîne C++ contenant des caractères non ASCII (sources JUCE de PRISME)."""
import re, sys

BS = chr(92)


def process(s):
    out, i, n, cnt = [], 0, len(s), 0
    while i < n:
        c = s[i]
        if c == '/' and i + 1 < n and s[i + 1] == '/':
            j = s.find('\n', i)
            j = n if j < 0 else j
            out.append(s[i:j]); i = j; continue
        if c == '/' and i + 1 < n and s[i + 1] == '*':
            j = s.find('*/', i + 2)
            j = n if j < 0 else j + 2
            out.append(s[i:j]); i = j; continue
        if c == "'":
            j = i + 1
            while j < n and s[j] != "'":
                j += 2 if s[j] == BS else 1
            out.append(s[i:j + 1]); i = j + 1; continue
        if c == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == BS else 1
            lit = s[i:j + 1]
            pre = "".join(out)[-4:]
            if any(ord(ch) > 127 for ch in lit) and not pre.endswith("U8 ("):
                lit = "U8 (" + lit + ")"
                cnt += 1
            out.append(lit); i = j + 1; continue
        out.append(c); i += 1
    return "".join(out), cnt


LIT = '"(?:[^"' + BS + BS + '\n]|' + BS + BS + '.)*"'
for p in sys.argv[1:]:
    s = open(p, encoding="utf-8").read()
    s = re.sub("juce::String::fromUTF8 " + BS + "((U8 " + BS + "(" + LIT + BS + "))" + BS + ")", lambda m: m.group(1), s)
    s = re.sub("juce::String::fromUTF8 " + BS + "(" + "(" + LIT + ")" + BS + ")", lambda m: "U8 (" + m.group(1) + ")", s)
    s, c = process(s)
    open(p, "w", encoding="utf-8").write(s)
    print(p, c)
