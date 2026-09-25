"""Patch v0.7 : la taille de la fenêtre est mémorisée dans un fichier utilisateur (AppData/Shawty/PRISME/ui.xml), plus dans l'état du projet (une valeur ancienne y restait et primait sur la nouvelle taille par défaut)."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")


def rd(n):
    return open(os.path.join(SRC, n), encoding="utf-8").read()


def wr(n, s):
    open(os.path.join(SRC, n), "w", encoding="utf-8").write(s)


e = rd("PluginEditor.cpp")
NL = chr(10)
helpers = '''static juce::File uiFile()
{
    return juce::File::getSpecialLocation (juce::File::userApplicationDataDirectory).getChildFile ("Shawty").getChildFile ("PRISME").getChildFile ("ui.xml");
}

// Largeur de fenetre memorisee entre les sessions et entre les projets (0 si absente)
static int loadWidth()
{
    if (auto xml = juce::parseXML (uiFile())) return xml->getIntAttribute ("width", 0);
    return 0;
}

static void saveWidth (int w)
{
    const auto f = uiFile();
    f.getParentDirectory().createDirectory();
    juce::XmlElement x ("PRISME_UI");
    x.setAttribute ("width", w);
    x.writeTo (f);
}

'''
marker = "// ------------------------------------------------------------------ courbe"
assert marker in e
e = e.replace(marker, helpers + marker, 1)

old = '    const int w = juce::jlimit (560, 2240, (int) proc.apvts.state.getProperty ("uiWidth", defaultW));      // taille memorisee (etat du plugin)'
if old not in e:
    i = e.index('proc.apvts.state.getProperty ("uiWidth"')
    j = e.rfind(NL, 0, i) + 1
    k = e.index(NL, i)
    old = e[j:k]
new = "    const int saved = loadWidth();                                                     // derniere taille utilisee (fichier utilisateur)" + NL + "    const int w = (saved >= 560 && saved <= 2240) ? saved : defaultW;"
e = e.replace(old, new, 1)

old2 = e[e.index('    if (getWidth() > 0) proc.apvts.state.setProperty ("uiWidth"'):]
old2 = old2[:old2.index(NL) + 1]
e = e.replace(old2, "    if (getWidth() > 0) { uiWidth = getWidth(); uiDirty = true; }" + NL, 1)

e = e.replace("PrismeEditor::~PrismeEditor()" + NL + "{" + NL + "    stopTimer();", "PrismeEditor::~PrismeEditor()" + NL + "{" + NL + "    stopTimer();" + NL + "    if (uiWidth > 0) saveWidth (uiWidth);", 1)
e = e.replace("void PrismeEditor::timerCallback()" + NL + "{" + NL, "void PrismeEditor::timerCallback()" + NL + "{" + NL + "    if (uiDirty && uiWidth == lastUiWidth) { saveWidth (uiWidth); uiDirty = false; }        // taille stable depuis un tick : on l'ecrit" + NL + "    lastUiWidth = uiWidth;" + NL, 1)
wr("PluginEditor.cpp", e)

h = rd("PluginEditor.h")
h = h.replace("    void layoutContent();", "    void layoutContent();" + NL + "    int uiWidth = 0, lastUiWidth = 0;" + NL + "    bool uiDirty = false;", 1)
wr("PluginEditor.h", h)
print("ok")
