import re, json, os, zipfile, sys, shutil
sys.path.insert(0, os.path.dirname(__file__))
from palettes import ALL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tpl = open(f"{ROOT}/gen/userChrome.template.css", encoding="utf-8").read()

# --- 2) kontrast ---
def lum(h):
    h=h.lstrip("#"); r,g,b=[int(h[i:i+2],16)/255 for i in (0,2,4)]
    f=lambda c: c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b)
def cr(a,b):
    la,lb=sorted([lum(a),lum(b)],reverse=True); return (la+0.05)/(lb+0.05)

def darken(h, fg, target):
    h=h.lstrip("#"); r,g,b=[int(h[i:i+2],16) for i in (0,2,4)]
    for _ in range(80):
        c="#%02X%02X%02X"%(r,g,b)
        if cr(fg,c)>=target: return c
        r,g,b=[int(v*0.97) for v in (r,g,b)]
    return c
for p in ALL:
    p["SEL_INACTIVE"]=darken(p["SEL_INACTIVE"],"#ffffff",4.5) if p["SCHEME"]=="light" else p["SEL_INACTIVE"]
    p["HDR_TOP"]=darken(p["HDR_TOP"],"#ffffff",3.2)
    p["HOV_BOT"]=darken(p["HOV_BOT"],p["TEXT"],4.6) if p["SCHEME"]=="dark" else p["HOV_BOT"]
print("\nKONTRAST (WCAG, cel >= 4.5 tekst, >= 3 nagłówek):")
bad=[]
for p in ALL:
    checks = {
     "biały na SEL": cr("#ffffff",p["SEL"]),
     "biały na HDR_BOT": cr("#ffffff",p["HDR_BOT"]),
     "biały na HDR_TOP": cr("#ffffff",p["HDR_TOP"]),
     "TEXT na WHITE": cr(p["TEXT"],p["WHITE"]),
     "TEXT na TOOLBAR": cr(p["TEXT"],p["TOOLBAR"]),
     "TEXT na PANE": cr(p["TEXT"],p["PANE"]),
     "TEXT na HOV": cr(p["TEXT"],p["HOV"]),
     "TEXT na HOV_BOT": cr(p["TEXT"],p["HOV_BOT"]),
     "TEXT na POPUP": cr(p["TEXT"],p["POPUP"]),
     "TEXT na BTN": cr(p["TEXT"],p["BTN"]),
     "biały na SEL_INACTIVE": cr("#ffffff",p["SEL_INACTIVE"]),
    }
    line=[]
    for k,v in checks.items():
        lim = 3 if "HDR_TOP" in k else 4.5
        flag = "" if v>=lim else " !!"
        if flag: bad.append((p["SLUG"],k,round(v,2)))
        line.append(f"{k}={v:.1f}{flag}")
    print(f"{p['SLUG']:9}", "; ".join(line))
print("\nPROBLEMY:", bad)

# --- 3) generowanie ---
with zipfile.ZipFile(f"{ROOT}/blue/outlook2003-blue-theme.xpi") as base_theme:
    manifest_src = json.loads(base_theme.read("manifest.json"))
dist = ROOT
usercontent = open(f"{ROOT}/gen/userContent.template.css",encoding="utf-8").read()
for p in ALL:
    d = f"{dist}/{p['SLUG']}"; os.makedirs(d, exist_ok=True)
    shutil.copytree(f"{ROOT}/gen/icons", f"{d}/icons", dirs_exist_ok=True)
    css = re.sub(r"@@([A-Z_]+)@@", lambda m: p[m.group(1)], tpl)
    assert "@@" not in css and css.count("{")==css.count("}")
    open(f"{d}/userChrome.css","w",encoding="utf-8").write(css)
    open(f"{d}/userContent.css","w",encoding="utf-8").write(re.sub(r"@@([A-Z_]+)@@", lambda match: p[match.group(1)], usercontent))
    m = json.loads(json.dumps(manifest_src))
    m["name"] = f"Outlook 2003 – {p['NAME']}"
    m["version"] = "1.4"
    m["browser_specific_settings"]["gecko"]["id"] = f"outlook2003-{p['SLUG']}@local.theme"
    m["theme"]["colors"] = {
     "frame":p["FRAME"],"frame_inactive":p["BAR_BOT"],"tab_background_text":p["TEXT"],"tab_text":p["TEXT"],
     "tab_selected":p["WHITE"],"tab_line":p["RING"],"toolbar":p["TOOLBAR"],"toolbar_text":p["TEXT"],
     "toolbar_field":p["WHITE"],"toolbar_field_text":p["TEXT"],"toolbar_field_border":p["INPUT_BORDER"],
     "toolbar_field_focus":p["WHITE"],"toolbar_field_border_focus":p["SEL"],
     "toolbar_field_highlight":p["SEL"],"toolbar_field_highlight_text":"#FFFFFF",
     "toolbar_top_separator":p["BORDER"],"toolbar_bottom_separator":p["BORDER"],"toolbar_vertical_separator":p["SEP"],
     "bookmark_text":p["TEXT"],"button_background_hover":p["HOV"],"button_background_active":p["ACTIVE"],
     "icon_color":p["ICON"],"popup":p["POPUP"],"popup_text":p["TEXT"],"popup_border":p["BORDER"],
     "popup_highlight":p["HOV"],"popup_highlight_text":p["TEXT"],"sidebar":p["PANE"],"sidebar_text":p["TEXT"],
     "sidebar_border":p["BORDER"],"sidebar_highlight":p["SEL"],"sidebar_highlight_text":"#FFFFFF",
     "tree_view":p["WHITE"],"tree_view_text":p["TEXT"]}
    m["theme"]["properties"] = {"color_scheme": p["SCHEME"]}
    m["description"] = f"Outlook 2003 – wariant {p['NAME']}."
    with zipfile.ZipFile(f"{d}/outlook2003-{p['SLUG']}-theme.xpi","w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(m, indent=2, ensure_ascii=False))
print("\nWygenerowano:", [p["SLUG"] for p in ALL])
