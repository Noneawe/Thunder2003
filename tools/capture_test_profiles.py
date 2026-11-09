#!/usr/bin/env python3
"""Capture real Thunderbird windows. Run inside xvfb-run from a normal terminal."""

import argparse
from contextlib import contextmanager
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

from create_test_profiles import ROOT, VARIANTS, moz_lz4, startup_state


OUTPUT = ROOT / "artifacts" / "gui"
SOURCE_PROFILES = ROOT / "TestProfiles"
LOCALE = "pl"
APP = os.environ.get("THUNDERBIRD_BINARY", str(ROOT / "runtime" / "thunderbird" / "thunderbird"))


class Marionette:
    def __init__(self, port):
        self.socket = socket.create_connection(("127.0.0.1", port), timeout=3)
        self.socket.settimeout(35)
        self.sequence = 0
        try:
            self.receive()
        except Exception:
            self.socket.close()
            raise

    def start_session(self):
        self.command("WebDriver:NewSession", {})
        self.command("Marionette:SetContext", {"value": "chrome"})

    def receive(self):
        length = bytearray()
        while True:
            char = self.socket.recv(1)
            if not char:
                raise ConnectionError("Thunderbird zamknął połączenie Marionette")
            if char == b":":
                break
            length.extend(char)
        data = bytearray()
        while len(data) < int(length):
            chunk = self.socket.recv(int(length) - len(data))
            if not chunk:
                raise ConnectionError("Niepełna odpowiedź Marionette")
            data.extend(chunk)
        return json.loads(data)

    def command(self, name, parameters):
        self.sequence += 1
        payload = json.dumps([0, self.sequence, name, parameters]).encode()
        self.socket.sendall(str(len(payload)).encode() + b":" + payload)
        while True:
            response = self.receive()
            if isinstance(response, list) and response[:2] == [1, self.sequence]:
                if response[2]:
                    raise RuntimeError(json.dumps(response[2], ensure_ascii=False))
                return response[3]

    def js(self, script, asynchronous=False):
        response = self.command(
            "WebDriver:ExecuteAsyncScript" if asynchronous else "WebDriver:ExecuteScript",
            {"script": script, "args": [], "newSandbox": True,
             "sandbox": "default", "filename": "capture_test_profiles.py", "line": 1},
        )
        return response.get("value") if isinstance(response, dict) else response


MAIN = """
var w = Services.wm.getMostRecentWindow('mail:3pane');
var tabmail = w?.document.getElementById('tabmail');
var p = tabmail?.currentTabInfo?.chromeBrowser?.contentWindow;
"""


def wait_for(check, timeout=45):
    end = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < end:
        try:
            value = check()
            if value:
                return value
        except (OSError, RuntimeError, ConnectionError) as exc:
            last_error = exc
        time.sleep(0.3)
    raise TimeoutError(f"Przekroczony czas oczekiwania: {last_error}")


def screenshot(folder, name):
    time.sleep(0.7)
    subprocess.run(["import", "-window", "root", str(folder / f"{name}.png")], check=True)


def check_button_icons(client, setup, expected, property_name="listStyleImage"):
    icons = client.js(setup + f"""
        var done = arguments[arguments.length - 1];
        Promise.all(Object.entries({json.dumps(expected)}).map(async ([id, filename]) => {{
            var button = win.document.getElementById(id);
            var value = win.getComputedStyle(button)[{json.dumps(property_name)}];
            var label = button.querySelector('.toolbarbutton-text') || button;
            var labelFits = win.getComputedStyle(label).display === 'none'
                || label.scrollWidth <= label.clientWidth + 1;
            var url = value.match(/url\\(["']?(.*?)["']?\\)/)?.[1];
            var image = new win.Image();
            var loaded = await new Promise(resolve => {{
                image.onload = () => resolve(image.naturalWidth === 24 && image.naturalHeight === 24);
                image.onerror = () => resolve(false);
                win.setTimeout(() => resolve(false), 4000);
                image.src = url || '';
            }});
            return {{id, url, filename, loaded, labelFits,
                label: button.getAttribute('label') || button.textContent.trim()}};
        }})).then(done);
    """, asynchronous=True)
    if not all(icon["loaded"] and icon["url"].startswith("file:")
               and icon["url"].endswith("/icons/" + icon["filename"] + ".svg")
               and icon["labelFits"] for icon in icons):
        raise AssertionError(f"Nie wczytano grafik przycisków: {icons}")
    return icons


@contextmanager
def window_manager():
    """Use the current WM, or run the project's Openbox for this Xvfb session."""
    def manager_name():
        prop = subprocess.check_output(["xprop", "-root", "_NET_SUPPORTING_WM_CHECK"], text=True)
        match = re.search(r"window id # (0x[0-9a-f]+)", prop)
        if match:
            return subprocess.check_output(["xprop", "-id", match[1], "_NET_WM_NAME"], text=True).strip()

    existing = manager_name()
    if existing:
        yield existing
        return
    local = ROOT / "runtime" / "openbox"
    executable = shutil.which("openbox") or str(local / "usr/bin/openbox")
    config = local / "etc/xdg/openbox/rc.xml"
    if not config.is_file():
        config = Path("/etc/xdg/openbox/rc.xml")
    env = {**os.environ,
           "LD_LIBRARY_PATH": str(local / "usr/lib/x86_64-linux-gnu") + ":" + os.environ.get("LD_LIBRARY_PATH", ""),
           "XDG_CACHE_HOME": str(OUTPUT / ".cache"),
           "XDG_DATA_DIRS": str(local / "usr/share") + ":" + os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")}
    with (OUTPUT / "window-manager.log").open("w") as log:
        manager = subprocess.Popen([executable, "--sm-disable", "--config-file", str(config)],
                                   env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            def ready():
                if manager.poll() is not None:
                    raise ValueError("Openbox zakończył działanie; sprawdź window-manager.log")
                return manager_name()
            yield wait_for(ready, timeout=10)
        finally:
            manager.terminate()
            manager.wait(timeout=5)


def capture_account_settings(client, folder, screenshots):
    client.js(MAIN + "w.MsgAccountManager('am-main.xhtml', p.gFolder.server);")
    account = MAIN + """
        var a=tabmail.currentTabInfo.browser?.contentWindow;
        var f=a?.document.getElementById('contentFrame')?.contentWindow;
    """
    wait_for(lambda: client.js(account + "return a?.currentPageId === 'am-main.xhtml' && !!f?.document.getElementById('identity.email');"))
    pages = [
        ("09-account-identity", "am-main.xhtml", ["server.prettyName", "identity.fullName", "identity.email"]),
        ("10-account-server", "am-server.xhtml", ["server.hostname", "server.port", "server.username", "server.socketType", "server.authMethod"]),
        ("11-account-copies", "am-copies.xhtml", []),
        ("12-account-composition", "am-addressing.xhtml", []),
        ("13-account-smtp", "am-smtp.xhtml", []),
    ]
    results = []
    for name, page, fields in pages:
        client.js(account + f"""
            var tree=a.document.getElementById('accounttree');
            tree.selectedIndex=tree.rows.findIndex(row=>row.getAttribute('PageTag') === {json.dumps(page)});
        """)
        wait_for(lambda: client.js(account + f"return f?.document.documentURI.endsWith('/' + {json.dumps(page)}) && f.document.readyState === 'complete';"))
        client.js(account + "f.scrollTo(0,0);")
        data = client.js(account + f"""
            var d=f.document;
            var fields={json.dumps(fields)}.map(id=>{{
                var e=d.getElementById(id),r=e?.getBoundingClientRect();
                return {{id,value:e?.value,rect:r?.toJSON()}};
            }});
            var heading=d.querySelector('.dialogheader-title, h1');
            var frame=a.document.getElementById('contentFrame').getBoundingClientRect();
            return {{page:{json.dumps(page)},title:heading?.textContent || heading?.getAttribute('value'),
                fields, width:f.innerWidth, scrollWidth:d.documentElement.scrollWidth,
                background:f.getComputedStyle(d.body).backgroundColor,
                text:f.getComputedStyle(d.body).color,
                frame:frame.toJSON(),
                tabTitle:tabmail.currentTabInfo.tabNode.label}};
        """)
        if data["scrollWidth"] > data["width"] + 1 or any(
                not field.get("rect") or field["rect"]["width"] <= 0
                or field["rect"]["left"] < 0 or field["rect"]["right"] > data["width"] + 1
                for field in data["fields"]):
            raise AssertionError(f"Ustawienia konta wychodzą poza szerokość panelu: {data}")
        if page == "am-main.xhtml" and data["fields"][2]["value"] != "test.user@example.test":
            raise AssertionError(f"Niepoprawna angielska tożsamość: {data}")
        if page == "am-server.xhtml" and [v["value"] for v in data["fields"][:3]] != ["127.0.0.1", "65534", "ui-test"]:
            raise AssertionError(f"Niepoprawne ustawienia serwera testowego: {data}")
        screenshot(folder, name)
        screenshots.append(name + ".png")
        results.append(data)
        (folder / "account-settings.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    # Native SMTP editor, opened as an account-manager subdialog.
    client.js(account + "f.document.getElementById('editButton').click();")
    dialog = account + "var s=a.gSubDialog?._topDialog; var d=s?._frame?.contentDocument;"
    wait_for(lambda: client.js(dialog + "return d?.documentURI?.includes('SmtpServerEdit.xhtml') && d.readyState === 'complete';"))
    smtp_editor = client.js(dialog + """
        return {page:d.documentURI,title:d.title,
            width:d.defaultView.innerWidth, scrollWidth:d.documentElement.scrollWidth,
            fields:Array.from(d.querySelectorAll('input')).map(e=>({id:e.id,value:e.value,rect:e.getBoundingClientRect().toJSON()}))};
    """)
    if smtp_editor["scrollWidth"] > smtp_editor["width"] + 1 or any(
            field["rect"]["left"] < 0 or field["rect"]["right"] > smtp_editor["width"] + 1
            for field in smtp_editor["fields"] if field["rect"]["width"] > 0):
        raise AssertionError(f"Edytor SMTP wychodzi poza szerokość dialogu: {smtp_editor}")
    results.append(smtp_editor)
    screenshot(folder, "14-account-smtp-edit")
    screenshots.append("14-account-smtp-edit.png")
    client.js(dialog + "d.querySelector('dialog').cancelDialog();")
    (folder / "account-settings.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    return results


def capture(variant):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    source = SOURCE_PROFILES / variant
    profile = OUTPUT / "profiles" / variant
    if profile.exists():
        raise FileExistsError(f"Kopia testowa już istnieje: {profile}; zachowaj ją lub przenieś przed ponownym testem")
    shutil.copytree(source, profile)
    prefs = profile / "prefs.js"
    prefs.write_text(prefs.read_text().replace(str(source), str(profile)))
    addon_id = f"outlook2003-{variant}@local.theme"
    # Regenerate the pending install state so it points at the disposable copy.
    if (profile / "extensions" / "staged" / f"{addon_id}.xpi").exists():
        (profile / "addonStartup.json.lz4").write_bytes(moz_lz4(startup_state(profile, addon_id)))
    (profile / "user.js").write_text(f'user_pref("marionette.port", {port});\n')
    folder = OUTPUT / variant
    folder.mkdir(exist_ok=True)
    result = {"variant": variant, "locale": LOCALE, "status": "failed", "screenshots": []}
    css = (source / "chrome" / "userChrome.css").read_text()
    hex_colors = {role: re.search(r"--o3-" + role + r":\s*(#[0-9A-Fa-f]{6})", css).group(1)
                  for role in ("surface", "popup", "text")}
    expected_colors = {role: "rgb(" + ", ".join(str(int(value[i:i+2], 16)) for i in (1, 3, 5)) + ")"
                       for role, value in hex_colors.items()}
    result["palette"] = {"expected": expected_colors}
    client = None
    with (folder / "thunderbird.log").open("w") as log:
        process = subprocess.Popen(
            [APP, "--no-remote", "--offline", "--profile", str(profile),
             "--marionette", "--remote-allow-system-access"],
            stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, "MOZ_ENABLE_WAYLAND": "0", "GDK_BACKEND": "x11",
                 "MOZ_REMOTE_ALLOW_SYSTEM_ACCESS": "1"},
        )
        try:
            def connect():
                if process.poll() is not None:
                    raise ValueError(f"Thunderbird zakończył działanie: {process.returncode}")
                return Marionette(port)

            client = wait_for(connect)
            # Retry only connection startup, never a partially created session.
            client.start_session()
            wait_for(lambda: client.js(MAIN + "return p?.gDBView?.rowCount > 0;"))
            initial_rows = client.js(MAIN + 'return p.threadTree.getAttribute("rows");')
            client.js('Services.prefs.setIntPref("mail.threadpane.listview", 1);')
            wait_for(lambda: client.js(MAIN + 'return p.threadTree.getAttribute("rows") === "thread-row" && !p.threadTree.headerHidden;'))
            client.js('Services.prefs.setIntPref("mail.threadpane.listview", 0);')
            wait_for(lambda: client.js(MAIN + 'return p.threadTree.getAttribute("rows") === "thread-card" && p.threadTree.headerHidden;'))
            result["view"] = client.js(MAIN + """
                return {mode: "cards", rows: p.threadTree.getAttribute("rows"),
                    headerHidden: p.threadTree.headerHidden,
                    preference: Services.prefs.getIntPref("mail.threadpane.listview"),
                    tableToCardsVerified: true};
            """)
            result["view"]["initialRows"] = initial_rows
            client.js('Services.prefs.setIntPref("mail.pane_config.dynamic", 2);')
            wait_for(lambda: client.js(MAIN + 'return p.paneLayout.classList.contains("layout-vertical");'))
            result["ui"] = client.js(MAIN + """
                return {version: Services.appinfo.version,
                    locale: Services.locale.appLocaleAsBCP47,
                    folder: p.gViewWrapper.displayedFolder.URI,
                    rows: p.gDBView.rowCount,
                    count: p.gViewWrapper.displayedFolder.getTotalMessages(false),
                    cssEnabled: Services.prefs.getBoolPref('toolkit.legacyUserProfileCustomizations.stylesheets'),
                    barTop: w.getComputedStyle(w.document.documentElement).getPropertyValue('--o3-bar-top').trim(),
                    folderBackground: p.getComputedStyle(p.document.getElementById('folderPane')).backgroundColor};
            """)
            result["theme"] = client.js(f"""
                var done = arguments[arguments.length - 1];
                var {{AddonManager}} = ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
                AddonManager.getAddonByID({json.dumps(addon_id)}).then(a =>
                    done(a ? {{id:a.id, active:a.isActive, disabled:a.userDisabled}} : null),
                    e => done({{error:String(e)}}));
            """, asynchronous=True)
            if not result["theme"] or not result["theme"].get("active"):
                raise AssertionError(f"Motyw XPI nie jest aktywny: {result['theme']}")
            if result["ui"]["count"] != 32 or not result["ui"]["barTop"]:
                raise AssertionError(f"Niepoprawne dane lub niewczytany CSS: {result['ui']}")
            if result["ui"]["locale"] != LOCALE:
                raise AssertionError(f"Niepoprawny język interfejsu: {result['ui']['locale']}")
            client.js(MAIN + "w.resizeTo(1440, 960); p.threadTree.selectedIndex = -1;")
            result["layout"] = client.js(MAIN + """
                var list = p.document.getElementById('threadPane').getBoundingClientRect();
                var preview = p.messagePane.getBoundingClientRect();
                return {mode: "vertical", preference: Services.prefs.getIntPref('mail.pane_config.dynamic'),
                    list: {x:list.x, y:list.y, width:list.width, height:list.height},
                    preview: {x:preview.x, y:preview.y, width:preview.width, height:preview.height},
                    sideBySide: preview.x >= list.right - 1 && Math.abs(preview.y-list.y) < 2
                        && list.width > 0 && preview.width > 0};
            """)
            if not result["layout"]["sideBySide"]:
                raise AssertionError(f'Panele nie są obok siebie: {result["layout"]}')
            wait_for(lambda: client.js(MAIN + 'return p.threadPane.rowCount === 2 && p.threadTree.classList.contains("cards-row-compact");'))
            result["usability"] = client.js(MAIN + """
                var folder = p.document.getElementById('folderPane').getBoundingClientRect();
                var card = p.threadTree.querySelector('tr[is="thread-card"]');
                return {cardRows: p.threadPane.rowCount,
                    compactCards: p.threadTree.classList.contains('cards-row-compact'),
                    interfaceFont: p.getComputedStyle(p.threadTree).fontSize,
                    firstSender: card?.querySelector(".sender")?.textContent,
                    addressFormat: Services.prefs.getIntPref("mail.addressDisplayFormat"),
                    folderFont: p.getComputedStyle(p.folderTree).fontSize,
                    folderWidth: folder.width,
                    cardHeight: card?.getBoundingClientRect().height,
                    nativeCardHeight: p.customElements.get('thread-card').ROW_HEIGHT};
            """)
            if (result["usability"]["interfaceFont"] != "13px"
                    or not 360 <= result["layout"]["list"]["width"] <= 420
                    or result["layout"]["preview"]["width"] < 740):
                raise AssertionError(f'Niepoprawne proporcje lub font: {result["layout"]}, {result["usability"]}')
            def menu_geometry():
                return client.js(MAIN + """
                    var bar = w.document.getElementById('toolbar-menubar');
                    var r = bar.getBoundingClientRect();
                    var labels = Array.from(bar.querySelectorAll('menubar > menu')).filter(e => e.getBoundingClientRect().height > 0).map(e => {
                        var text = e.querySelector('.menubar-text');
                        return (text || e).getBoundingClientRect();
                    });
                    return {height:r.height, inactive:bar.getAttribute('inactive'),
                        padding:w.getComputedStyle(bar).padding, labelCount:labels.length,
                        labelsFit:labels.length > 0 && labels.every(x => x.top >= r.top && x.bottom <= r.bottom)};
                """)

            result["menubar"] = {"hidden": menu_geometry()}
            if result["menubar"]["hidden"]["height"] != 0:
                raise AssertionError(f'Ukryty pasek menu pozostawia widoczny fragment: {result["menubar"]}')
            client.js(MAIN + "w.focus();")
            main_window = subprocess.check_output(["xdotool", "search", "--onlyvisible", "--name", "Thunderbird"], text=True).splitlines()[0]
            subprocess.run(["xdotool", "windowactivate", "--sync", main_window], check=True)
            subprocess.run(["xdotool", "key", "--clearmodifiers", "Alt_L"], check=True)
            wait_for(lambda: menu_geometry()["height"] > 15)
            result["menubar"]["keyboard"] = menu_geometry()
            screenshot(folder, "06-menubar-keyboard")
            result["screenshots"].append("06-menubar-keyboard.png")
            subprocess.run(["xdotool", "key", "--clearmodifiers", "Escape"], check=True)
            wait_for(lambda: menu_geometry()["height"] == 0)
            # Also check the persistent visible state without changing the source profile.
            client.js(MAIN + "var bar=w.document.getElementById('toolbar-menubar'); bar.removeAttribute('autohide'); bar.removeAttribute('inactive');")
            result["menubar"]["persistent"] = menu_geometry()
            if not all(result["menubar"][state]["labelsFit"] for state in ("keyboard", "persistent")):
                raise AssertionError(f'Widoczny pasek obcina etykiety: {result["menubar"]}')
            client.js(MAIN + "var bar=w.document.getElementById('toolbar-menubar'); bar.setAttribute('autohide','true'); bar.setAttribute('inactive','true');")
            wait_for(lambda: menu_geometry()["height"] == 0)
            result["icons"] = {"folder": check_button_icons(client, MAIN + "var win=p;", {
                "folderPaneWriteMessage": "new-message", "folderPaneGetMessages": "get-mail",
            }, "backgroundImage")}
            screenshot(folder, "01-inbox")
            result["screenshots"].append("01-inbox.png")
            client.js(MAIN + """
                for (var i=0; i<p.gDBView.rowCount; i++) {
                    if (p.gDBView.getMsgHdrAt(i).messageId == 'demo-Inbox-0@example.test') {
                        p.threadTree.selectedIndex=i;
                        p.threadTree.focus();
                        break;
                    }
                }
            """)
            wait_for(lambda: client.js(MAIN + "return p.messageBrowser?.contentWindow?.currentAttachments?.length === 2;"))
            result["message"] = client.js(MAIN + """
                var m = p.messageBrowser.contentWindow;
                m.toggleAttachmentList(true);
                return {uri: m.gMessageURI, attachments: m.currentAttachments.map(a => a.name)};
            """)
            result["header"] = client.js(MAIN + """
                var m = p.messageBrowser.contentWindow;
                var subject = m.document.getElementById('headerSubjectSecurityContainer').getBoundingClientRect();
                var sender = m.document.getElementById('headerSenderToolbarContainer').getBoundingClientRect();
                var ids = ['hdrReplyToSenderButton','hdrReplyButton','hdrReplyAllButton','hdrReplyListButton',
                    'hdrFollowupButton','hdrForwardButton','hdrArchiveButton','hdrJunkButton','hdrTrashButton','otherActionsButton'];
                var buttons = ids.map(id => m.document.getElementById(id)).filter(b => b?.getBoundingClientRect().width > 0);
                return {subjectFirst: subject.top < sender.top,
                    subjectFont: m.getComputedStyle(m.document.getElementById('expandedsubjectBox')).fontSize,
                    height: m.document.getElementById('messageHeader').getBoundingClientRect().height,
                    buttons: buttons.map(b => ({id: b.id, label: b.getAttribute('label'),
                        textVisible: m.getComputedStyle(b.querySelector('.toolbarbutton-text')).display !== 'none'}))};
            """)
            text_buttons = [b["id"] for b in result["header"]["buttons"] if b["textVisible"]]
            if LOCALE == "en-US" and {b["label"] for b in result["header"]["buttons"] if b["textVisible"]} != {"Reply", "Forward", "Delete", "More"}:
                raise AssertionError(f'Niepoprawne angielskie etykiety: {result["header"]}')
            if (not result["header"]["subjectFirst"] or result["header"]["subjectFont"] != "16px"
                    or len(text_buttons) != 4 or not {"hdrForwardButton", "hdrTrashButton", "otherActionsButton"}.issubset(text_buttons)):
                raise AssertionError(f'Niepoprawny nagłówek: {result["header"]}')
            result["icons"]["header"] = check_button_icons(client, MAIN + "var win=p.messageBrowser.contentWindow;", {
                "hdrReplyToSenderButton": "reply", "hdrReplyAllButton": "reply-all",
                "hdrForwardButton": "forward", "hdrArchiveButton": "archive",
                "hdrJunkButton": "junk", "hdrTrashButton": "delete",
            })
            screenshot(folder, "02-message-html-attachments")
            result["screenshots"].append("02-message-html-attachments.png")
            reply = MAIN + "var m=p.messageBrowser.contentWindow; var b=m.document.getElementById('hdrReplyToSenderButton');"
            point = client.js(reply + "var r=b.getBoundingClientRect(); return [m.mozInnerScreenX+r.x+r.width/2,m.mozInnerScreenY+r.y+r.height/2];")
            subprocess.run(["xdotool", "mousemove", "--sync", *map(lambda value: str(round(value)), point)], check=True)
            wait_for(lambda: client.js(reply + "return b.matches(':hover');"))
            result["icons"]["hover"] = client.js(reply + "return m.getComputedStyle(b).backgroundImage;")
            screenshot(folder, "07-button-hover")
            result["screenshots"].append("07-button-hover.png")
            subprocess.run(["xdotool", "mousedown", "1"], check=True)
            try:
                wait_for(lambda: client.js(reply + "return b.matches(':active');"))
                result["icons"]["pressed"] = client.js(reply + "return m.getComputedStyle(b).backgroundImage;")
                if result["icons"]["pressed"] == result["icons"]["hover"]:
                    raise AssertionError('Przycisk nie zmienia wyglądu po wciśnięciu')
                screenshot(folder, "08-button-pressed")
                result["screenshots"].append("08-button-pressed.png")
            finally:
                # Release outside the button so the visual test does not trigger Reply.
                subprocess.run(["xdotool", "mousemove", "0", "999", "mouseup", "1"], check=True)
            client.js(MAIN + "p.messageBrowser.contentWindow.document.getElementById('otherActionsButton').click();")
            wait_for(lambda: client.js(MAIN + "return p.messageBrowser.contentWindow.document.getElementById('otherActionsPopup').state === 'open';"))
            result["header"]["moreMenuItems"] = client.js(MAIN + """
                var m = p.messageBrowser.contentWindow;
                return Array.from(m.document.querySelectorAll('#otherActionsPopup > menuitem, #otherActionsPopup > menu'))
                    .filter(e => !e.hidden && e.getBoundingClientRect().height > 0).length;
            """)
            if result["header"]["moreMenuItems"] < 5:
                raise AssertionError('Menu Więcej nie udostępnia oczekiwanych poleceń')
            screenshot(folder, "05-more-actions")
            result["screenshots"].append("05-more-actions.png")
            client.js(MAIN + "p.messageBrowser.contentWindow.document.getElementById('otherActionsPopup').hidePopup();")
            windows = subprocess.check_output(
                ["xdotool", "search", "--onlyvisible", "--name", "Thunderbird"], text=True,
            ).splitlines()
            subprocess.run(["xdotool", "windowfocus", "--sync", windows[0]], check=True)
            client.js(MAIN + "w.document.getElementById('button-appmenu').click();")
            wait_for(lambda: client.js(MAIN + "return w.document.getElementById('appMenu-popup').state === 'open';"))
            result["palette"]["menuBackground"] = client.js(MAIN + "return w.getComputedStyle(w.document.querySelector('#appMenu-popup panelview')).backgroundColor;")
            if result["palette"]["menuBackground"] != expected_colors["popup"]:
                raise AssertionError(f'Menu nie używa palety: {result["palette"]}')
            screenshot(folder, "03-menu")
            result["screenshots"].append("03-menu.png")
            client.js(MAIN + "w.document.getElementById('appMenu-popup').hidePopup();")
            client.js(MAIN + "w.goDoCommand('cmd_newMessage');")
            wait_for(lambda: client.js("""
                var c=Services.wm.getMostRecentWindow('msgcompose');
                return c?.document.readyState=='complete' && !!c.gMsgCompose?.editor;
            """))
            compose_text = ({"recipient": "anna.wilson@studio.example.test",
                             "subject": "Interface test — new message",
                             "body": "Hello Anna,\n\nThis is a sample reply to check the interface.\nAccents and punctuation: café, résumé — review complete.\n\nBest regards,\nTest User"}
                            if LOCALE == "en-US" else
                            {"recipient": "anna.kowalska@studio.example.test",
                             "subject": "Test interfejsu — nowa wiadomość",
                             "body": "Cześć Anno,\n\nTo przykładowa odpowiedź do sprawdzenia interfejsu.\nZażółć gęślą jaźń — ĄĆĘŁŃÓŚŹŻ.\n\nPozdrawiam,\nUżytkownik Testowy"})
            client.js("var fixture=" + json.dumps(compose_text) + ";" + """
                var c=Services.wm.getMostRecentWindow('msgcompose');
                c.resizeTo(1280,900);
                c.moveTo(80,30);
                c.focus();
                c.document.getElementById('toAddrInput').value=fixture.recipient;
                c.document.getElementById('msgSubject').value=fixture.subject;
                c.GetCurrentEditor().insertText(fixture.body);
            """)
            result["palette"]["editor"] = client.js("""
                var c = Services.wm.getMostRecentWindow('msgcompose');
                var d = c.GetCurrentEditor().document;
                var style = d.defaultView.getComputedStyle(d.body);
                return {url: d.documentURI, background: style.backgroundColor, text: style.color,
                    fieldBackground: c.getComputedStyle(c.document.getElementById('msgSubject')).backgroundColor,
                    fieldText: c.getComputedStyle(c.document.getElementById('msgSubject')).color,
                    serializedHtml: c.GetCurrentEditor().outputToString('text/html', 0)};
            """)
            editor = result["palette"]["editor"]
            serialized = editor.pop("serializedHtml").lower()
            custom_colors = [v.lower() for v in hex_colors.values() if v.lower() not in ("#ffffff", "#000000")]
            editor["paletteLeakedIntoMessage"] = any(value in serialized for value in custom_colors)
            if (editor["background"] != expected_colors["surface"] or editor["text"] != expected_colors["text"]
                    or editor["fieldBackground"] != expected_colors["surface"] or editor["fieldText"] != expected_colors["text"]
                    or editor["paletteLeakedIntoMessage"]):
                raise AssertionError(f'Edytor lub pole nie używa palety: {editor}')
            compose_window = subprocess.check_output(["xdotool", "getactivewindow"], text=True).strip()
            frame = subprocess.check_output(["xprop", "-id", compose_window, "_NET_FRAME_EXTENTS", "_NET_WM_ALLOWED_ACTIONS"], text=True)
            match = re.search(r"_NET_FRAME_EXTENTS\(CARDINAL\) = (\d+), (\d+), (\d+), (\d+)", frame)
            if not match or int(match[3]) < 10 or not all("_NET_WM_ACTION_" + action in frame for action in ("MINIMIZE", "MAXIMIZE_HORZ", "CLOSE")):
                raise AssertionError(f'Okno pisania nie ma pełnej belki menedżera okien: {frame}')
            result["windowManager"] = {"composeFrameExtents": list(map(int, match.groups())),
                                       "minimizeMaximizeClose": True}
            result["icons"]["compose"] = check_button_icons(client, "var win=Services.wm.getMostRecentWindow('msgcompose');", {
                "button-send": "send", "button-save": "save", "button-contacts": "address-book",
                "button-attach": "attach", "spellingButton": "spelling",
            })
            result["icons"]["disabledSend"] = client.js("""
                var c=Services.wm.getMostRecentWindow('msgcompose');
                var b=c.document.getElementById('button-send');
                return {disabled:b.disabled, filter:c.getComputedStyle(b.querySelector('.toolbarbutton-icon')).filter};
            """)
            if not result["icons"]["disabledSend"]["disabled"] or result["icons"]["disabledSend"]["filter"] != "grayscale(1)":
                raise AssertionError('Niepoprawny wygląd nieaktywnego przycisku wysyłania')
            screenshot(folder, "04-compose")
            result["screenshots"].append("04-compose.png")
            client.js("""
                var c=Services.wm.getMostRecentWindow('msgcompose');
                c.gContentChanged=false;
                if(c.gMsgCompose) c.gMsgCompose.bodyModified=false;
                c.close();
            """)
            if LOCALE == "en-US":
                result["accountSettings"] = capture_account_settings(client, folder, result["screenshots"])
            result["status"] = "passed"
        except Exception as exc:
            result["error"] = str(exc)
            try:
                screenshot(folder, "failure")
            except Exception:
                pass
        finally:
            if client:
                try:
                    client.command("Marionette:Quit", {"flags": ["eAttemptQuit"]})
                except Exception:
                    pass
                client.socket.close()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Osobny katalog wyników i kopii profili")
    parser.add_argument("--locale", choices=("pl", "en-US"), default="pl")
    parser.add_argument("--profiles", type=Path, help="Source profiles directory")
    parser.add_argument("variants", nargs="*", metavar="VARIANT")
    arguments = parser.parse_args()
    LOCALE = arguments.locale
    SOURCE_PROFILES = arguments.profiles.resolve() if arguments.profiles else ROOT / ("TestProfiles-en-US" if LOCALE == "en-US" else "TestProfiles")
    if LOCALE == "en-US" and "THUNDERBIRD_BINARY" not in os.environ:
        APP = str(ROOT / "runtime/thunderbird-en-US/thunderbird")
    OUTPUT = arguments.output.resolve()
    if not Path(APP).is_file() or not os.access(APP, os.X_OK):
        sys.exit("Brak lokalnego Thunderbirda. Uruchom: bash tools/download_thunderbird.sh")
    if not os.environ.get("DISPLAY"):
        sys.exit("Uruchom przez xvfb-run; wymagany jest DISPLAY.")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    variants = arguments.variants or list(VARIANTS)
    if any(variant not in VARIANTS for variant in variants):
        parser.error("Nieznany wariant motywu.")
    print(f"Katalog wyników: {OUTPUT}", flush=True)
    with window_manager() as manager:
        print(f"Menedżer okien: {manager}", flush=True)
        results = [capture(variant) for variant in variants]
    (OUTPUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(0 if all(r["status"] == "passed" for r in results) else 1)
