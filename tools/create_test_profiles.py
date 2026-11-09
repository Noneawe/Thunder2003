#!/usr/bin/env python3
"""Create isolated Thunderbird 159 demo profiles without touching real profiles."""

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage
from email.utils import format_datetime
import html
import json
import mailbox
from pathlib import Path
import random
import shutil
import struct
import zipfile

import demo_content_en as english


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "TestProfiles"
VARIANTS = ("blue", "silver", "graphite", "mocha", "sage", "aurora")
IDENTITY = "test.uzytkownik@example.test"
LOCALE = "pl"
FOLDERS = {
    "Inbox": 32, "Sent": 8, "Drafts": 3, "Templates": 2,
    "Archives": 6, "Trash": 4, "Junk": 3,
    "Projekty": 0, "Projekty.sbd/Atlas": 8, "Faktury": 6,
}
SUBJECTS = (
    "Spotkanie zespołu — piątek, godzina 10:30",
    "Projekt Atlas: propozycja nowego układu",
    "Faktura FV/2026/1106 — dokumenty do sprawdzenia",
    "Rezerwacja wyjazdu: potwierdzenie i szczegóły",
    "Raport tygodniowy: wyniki i następne kroki",
    "Zdjęcia z warsztatów — materiały dla uczestników",
    "Ważne: akceptacja makiety przed prezentacją",
    "Newsletter listopadowy — aktualności produktowe",
    "Krótka wiadomość",
    "Zażółć gęślą jaźń — test polskich znaków ĄĆĘŁŃÓŚŹŻ",
    "Długi temat wiadomości do sprawdzenia przy wąskiej kolumnie i zmniejszonym oknie programu",
    "Zamówienie #4821 — zmiana terminu dostawy",
    "Zaproszenie na warsztaty projektowe",
    "Budżet — tabela kosztów i podsumowanie",
    "Status wdrożenia: gotowe do przeglądu",
    "Plan na kolejny tydzień",
)
SENDERS = (
    ("Anna Kowalska", "anna.kowalska@studio.example.test"),
    ("Michał Nowak", "michal.nowak@atlas.example.test"),
    ("Natalia Wiśniewska", "natalia@biuro.example.test"),
    ("Piotr Zieliński", "piotr.zielinski@projekty.example.test"),
    ("Julia Wójcik", "julia@warsztaty.example.test"),
    ("Dział rozliczeń", "faktury@finanse.example.test"),
    ("Newsletter Studio", "aktualnosci@studio.example.test"),
)


def moz_lz4(value):
    # A single literal-only LZ4 block; no compression dependency is needed.
    data = json.dumps(value, ensure_ascii=False).encode()
    length = len(data) - 15
    extra = bytes([255]) * (length // 255) + bytes([length % 255])
    return b"mozLz40\0" + struct.pack("<I", len(data)) + b"\xf0" + extra + data


def startup_state(profile, addon_id):
    # Thunderbird 159's normal pending-install mechanism imports userDisabled.
    # Simply dropping a theme XPI in extensions/ would leave the theme disabled.
    return {"app-profile": {
        "path": str(profile / "extensions"), "addons": {},
        "staged": {addon_id: {
            "version": "1.4", "userDisabled": False, "softDisabled": False,
            "sourceURI": (ROOT / "Theme" / profile.name /
                          f"outlook2003-{profile.name}-theme.xpi").as_uri(),
        }},
    }}


def message(folder, index, locale="pl"):
    is_english = locale == "en-US"
    subjects = english.SUBJECTS if is_english else SUBJECTS
    identity = english.IDENTITY if is_english else IDENTITY
    user_name = "Test User" if is_english else "Użytkownik Testowy"
    rng = random.Random(159_000 + index)
    sender_name, sender_address = rng.choice(english.SENDERS if is_english else SENDERS)
    msg = EmailMessage(policy=policy.default)
    outgoing = folder in ("Sent", "Drafts", "Templates")
    msg["From"] = (f"{user_name} <{identity}>" if outgoing else
                   f"{sender_name} <{sender_address}>")
    msg["To"] = (f"{sender_name} <{sender_address}>" if outgoing else
                 f"{user_name} <{identity}>")
    topic = index % len(subjects)
    reply = folder == "Inbox" and index >= 16
    msg["Subject"] = ("Re: " if reply else "") + subjects[topic]
    msg["Date"] = format_datetime(datetime.now(timezone.utc).replace(
        hour=12, minute=0, second=0, microsecond=0)
        - timedelta(hours=(31 - index if folder == "Inbox" else index + 12) * 3))
    msg["Message-ID"] = f"<demo-{folder.replace('/', '-')}-{index}@example.test>"
    if reply:
        msg["In-Reply-To"] = f"<demo-Inbox-{index - 16}@example.test>"
        msg["References"] = msg["In-Reply-To"]
    if index % 6 == 0:
        msg["Cc"] = ("Project Team <team@atlas.example.test>" if is_english else
                     "Zespół projektowy <zespol@atlas.example.test>")
    if index % 8 == 0:
        msg["X-Priority"] = "1"
    flags = (1 if outgoing or index % 3 == 0 else 0)
    flags |= 4 if index % 7 == 0 else 0
    flags |= 2 if index % 9 == 0 else 0
    msg["X-Mozilla-Status"] = f"{flags:04x}"
    msg["X-Mozilla-Status2"] = "00000000"
    msg["X-Mozilla-Keys"] = f"$label{index % 5 + 1}" if index % 4 == 0 else ""
    body = (
        f"Cześć!\n\n{SUBJECTS[topic]}\n\n"
        "To fikcyjna wiadomość do testowania interfejsu Thunderbirda. "
        "Możesz ją otworzyć, oznaczyć, przenieść do folderu lub usunąć.\n\n"
        "Do omówienia:\n1. Układ paneli i czytelność tekstu.\n"
        "2. Zaznaczenie wiadomości i działanie menu.\n"
        "3. Wygląd załączników i okna odpowiedzi.\n\n"
        "Szczegóły: https://projekt.example.test/podglad\n\n"
        f"Pozdrawiam,\n{sender_name}\n"
    )
    if topic == 8:
        body = "Cześć, potwierdzam termin. Miłego dnia!\n"
    if topic == 10:
        body += "\n" + ("Przykładowy dłuższy akapit do sprawdzenia zawijania tekstu. " * 18)
    if reply:
        body += "\nDnia poprzedniego napisano:\n> Proszę o potwierdzenie terminu.\n> Dziękuję!\n"
    if is_english:
        body = english.body(subjects[topic], sender_name, topic, reply)
    msg.set_content(body)
    if index % 3 == 0:
        msg.add_alternative(
            "<!doctype html><html><body>"
            f"<h2>{html.escape(subjects[topic])}</h2>"
            f"<p>{html.escape(body).replace(chr(10), '<br>')}</p>"
            "<table border='1' cellpadding='8' style='border-collapse:collapse'>"
            + (english.TABLE if is_english else
            "<tr><th>Pozycja</th><th>Status</th><th>Kwota</th></tr>"
            "<tr><td>Projekt interfejsu</td><td>Do akceptacji</td><td>1 250,00 zł</td></tr>"
            "<tr><td>Warsztaty</td><td>Gotowe</td><td>480,00 zł</td></tr></table>"
            "<p><strong>Pogrubienie</strong>, <em>kursywa</em> i "
            "<a href='https://projekt.example.test'>przykładowy odnośnik</a>.</p>")
            + "</body></html>", subtype="html")
    if index % 5 == 0:
        msg.add_attachment(
            ("Product,Quantity,Price\nDesign,2,1250.00\nWorkshop,1,480.00\n" if is_english else
             "Produkt,Ilość,Cena\nMakieta,2,1250.00\nWarsztaty,1,480.00\n").encode(),
            maintype="text", subtype="csv", filename="november-summary.csv" if is_english else "zestawienie-listopad.csv")
    if index % 7 == 0:
        msg.add_attachment(("Sample meeting notes.\nReview the layout and follow-up actions.\n" if is_english else
                            "Przykładowe notatki do spotkania.\nZażółć gęślą jaźń.\n").encode(),
                           maintype="text", subtype="plain", filename="meeting-notes.txt" if is_english else "notatki-ze-spotkania.txt")
    return msg


def create_profile(variant):
    profile = OUTPUT / variant
    profile.mkdir()  # Refuse to overwrite a profile containing the user's test changes.
    chrome = profile / "chrome"
    chrome.mkdir()
    for filename in ("userChrome.css", "userContent.css"):
        shutil.copy2(ROOT / "Theme" / variant / filename, chrome / filename)
    shutil.copytree(ROOT / "Theme" / variant / "icons", chrome / "icons")
    xpi = ROOT / "Theme" / variant / f"outlook2003-{variant}-theme.xpi"
    with zipfile.ZipFile(xpi) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    addon_id = manifest["browser_specific_settings"]["gecko"]["id"]
    staged = profile / "extensions" / "staged"
    staged.mkdir(parents=True)
    shutil.copy2(xpi, staged / f"{addon_id}.xpi")
    (profile / "addonStartup.json.lz4").write_bytes(moz_lz4(startup_state(profile, addon_id)))

    maildir = profile / "Mail" / "TestMailbox"
    maildir.mkdir(parents=True)
    (profile / "Mail" / "Local Folders").mkdir()
    for folder, count in FOLDERS.items():
        target = maildir / folder
        target.parent.mkdir(exist_ok=True)
        with closing(mailbox.mbox(target)) as box:
            for index in range(count):
                box.add(message(folder, index, LOCALE))

    prefs = {
        "toolkit.legacyUserProfileCustomizations.stylesheets": True,
        "extensions.activeThemeID": addon_id,
        "extensions.pendingOperations": True,
        "mail.accountmanager.accounts": "account1,account2",
        "mail.accountmanager.defaultaccount": "account1",
        "mail.accountmanager.localfoldersserver": "server2",
        "mail.account.account1.server": "server1",
        "mail.account.account1.identities": "id1",
        "mail.account.account2.server": "server2",
        "mail.server.server1.type": "pop3",
        "mail.server.server1.hostname": "127.0.0.1",
        "mail.server.server1.port": 65534,
        "mail.server.server1.userName": "ui-test",
        "mail.server.server1.name": f"{'Test Mailbox' if LOCALE == 'en-US' else 'Skrzynka testowa'} — {variant.title()}",
        "mail.server.server1.directory": str(maildir),
        "mail.server.server1.directory-rel": "[ProfD]Mail/TestMailbox",
        "mail.server.server1.storeContractID": "@mozilla.org/msgstore/berkeleystore;1",
        "mail.server.server1.login_at_startup": False,
        "mail.server.server1.check_new_mail": False,
        "mail.server.server1.download_on_biff": False,
        "mail.server.server1.leave_on_server": True,
        "mail.server.server1.spamLevel": 0,
        "mail.server.server1.valid": True,
        "mail.server.server2.type": "none",
        "mail.server.server2.hostname": "Local Folders",
        "mail.server.server2.userName": "nobody",
        "mail.server.server2.name": "Local Folders" if LOCALE == "en-US" else "Foldery lokalne",
        "mail.server.server2.directory": str(profile / "Mail" / "Local Folders"),
        "mail.server.server2.directory-rel": "[ProfD]Mail/Local Folders",
        "mail.server.server2.storeContractID": "@mozilla.org/msgstore/berkeleystore;1",
        "mail.identity.id1.fullName": "Test User" if LOCALE == "en-US" else "Użytkownik Testowy",
        "mail.identity.id1.useremail": english.IDENTITY if LOCALE == "en-US" else IDENTITY,
        "mail.identity.id1.valid": True,
        "mail.identity.id1.smtpServer": "smtp1",
        "mail.identity.id1.fcc_folder": "mailbox://ui-test@127.0.0.1/Sent",
        "mail.identity.id1.draft_folder": "mailbox://ui-test@127.0.0.1/Drafts",
        "mail.identity.id1.stationery_folder": "mailbox://ui-test@127.0.0.1/Templates",
        "mail.identity.id1.archive_folder": "mailbox://ui-test@127.0.0.1/Archives",
        "mail.identity.id1.compose_html": True,
        "mail.smtpservers": "smtp1",
        "mail.smtp.defaultserver": "smtp1",
        "mail.smtpserver.smtp1.hostname": "127.0.0.1",
        "mail.smtpserver.smtp1.port": 65534,
        "mail.smtpserver.smtp1.authMethod": 1,
        "mail.smtpserver.smtp1.try_ssl": 0,
        "mail.smtpserver.smtp1.description": "Local test — no delivery" if LOCALE == "en-US" else "Test lokalny — bez wysyłania",
        "intl.locale.requested": LOCALE,
        "mail.shell.checkDefaultClient": False,
        "mailnews.start_page.enabled": False,
        "mail.provider.enabled": False,
        "mailnews.default_sort_order": 2,
        "mailnews.default_sort_type": 18,
        "mailnews.default_view_flags": 0,
        "mail.threadpane.listview": 0,
        "mail.threadpane.cardsview.rowcount": 2,
        "mail.uifontsize": 13,
        "mail.addressDisplayFormat": 2,
        "mail.pane_config.dynamic": 2,
        "mail.uidensity": 0,
        "offline.startup_state": 3,
        "offline.autoDetect": False,
        "network.manage-offline-status": False,
        "mailnews.tags.$label1.tag": "Ważne",
        "mailnews.tags.$label2.tag": "Praca",
        "mailnews.tags.$label3.tag": "Osobiste",
        "mailnews.tags.$label4.tag": "Do zrobienia",
        "mailnews.tags.$label5.tag": "Później",
    }
    if LOCALE == "en-US":
        for i, label in enumerate(("Important", "Work", "Personal", "To Do", "Later"), 1):
            prefs[f"mailnews.tags.$label{i}.tag"] = label
    (profile / "prefs.js").write_text(
        "// Profil testowy Outlook 2003. Fikcyjne wiadomości, bez prawdziwego konta.\n" +
        "".join(f"user_pref({json.dumps(key)}, {json.dumps(value, ensure_ascii=True)});\n"
                for key, value in prefs.items()), encoding="utf-8")
    session = {"rev": 0, "windows": [{"type": "3pane", "tabs": {
        "rev": 0, "selectedIndex": 0, "tabs": [{"mode": "mail3PaneTab", "state": {
            "firstTab": True, "folderURI": "mailbox://ui-test@127.0.0.1/Inbox",
            "folderPaneVisible": True, "messagePaneVisible": True,
        }, "ext": {}}],
    }}]}
    (profile / "session.json").write_text(json.dumps(session), encoding="utf-8")
    (profile / "xulstore.json").write_text(json.dumps({
        "chrome://messenger/content/messenger.xhtml": {
            "messengerWindow": {"width": "1440", "height": "940", "sizemode": "normal"},
            "toolbar-menubar": {"autohide": "true"},
            "folderPaneBox": {"width": "220"},
            "messagepaneboxwrapper": {"width": "780"},
        },
    }), encoding="utf-8")
    desktop = OUTPUT / f"Outlook2003-{variant}.desktop"
    desktop.write_text(
        "[Desktop Entry]\nType=Application\n"
        f"Name=Outlook 2003 — {variant.title()} (test)\n"
        f'Exec="{OUTPUT / "open.sh"}" {variant}\n'
        "Icon=thunderbird\nTerminal=false\nCategories=Network;Email;\n", encoding="utf-8")
    desktop.chmod(0o755)


def check():
    for variant in VARIANTS:
        profile = OUTPUT / variant
        for css in ("userChrome.css", "userContent.css"):
            assert (profile / "chrome" / css).read_bytes() == (ROOT / "Theme" / variant / css).read_bytes()
        for icon in (ROOT / "Theme" / variant / "icons").iterdir():
            assert (profile / "chrome" / "icons" / icon.name).read_bytes() == icon.read_bytes()
        total = unread = attachments = replies = 0
        for folder, count in FOLDERS.items():
            with closing(mailbox.mbox(profile / "Mail" / "TestMailbox" / folder, create=False)) as box:
                assert len(box) == count, (variant, folder, len(box), count)
                for msg in box:
                    total += 1
                    unread += not (int(msg["X-Mozilla-Status"], 16) & 1)
                    attachments += any(part.get_content_disposition() == "attachment" for part in msg.walk())
                    replies += msg["In-Reply-To"] is not None
                    assert msg["From"] and msg["To"] and msg["Message-ID"]
        assert total == sum(FOLDERS.values()) and unread and attachments and replies
        data = (profile / "addonStartup.json.lz4").read_bytes()
        assert data[:8] == b"mozLz40\0"
        # Decode the literal-only block and verify its pending install metadata.
        pos, length = 13, data[12] >> 4
        if length == 15:
            while True:
                chunk = data[pos]
                pos += 1
                length += chunk
                if chunk < 255:
                    break
        payload = data[pos:]
        assert length == len(payload) == struct.unpack("<I", data[8:12])[0]
        state = json.loads(payload)["app-profile"]
        addon_id, metadata = next(iter(state["staged"].items()))
        assert metadata["userDisabled"] is False
        with zipfile.ZipFile(profile / "extensions" / "staged" / f"{addon_id}.xpi") as archive:
            assert json.loads(archive.read("manifest.json"))["browser_specific_settings"]["gecko"]["id"] == addon_id
        assert json.loads((profile / "session.json").read_text())["windows"][0]["tabs"]["tabs"][0]["state"]["folderURI"].endswith("/Inbox")
        print(f"{variant:9}: {total} wiadomości, {unread} nieprzeczytanych, "
              f"{attachments} z załącznikami, {replies} odpowiedzi — OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale", choices=("pl", "en-US"), default="pl")
    parser.add_argument("--output", type=Path, help="Separate source profiles directory")
    parser.add_argument("--check", action="store_true", help="Sprawdź przygotowane profile bez zmieniania ich")
    args = parser.parse_args()
    LOCALE = args.locale
    if LOCALE == "en-US":
        FOLDERS = english.FOLDERS
    OUTPUT = args.output.resolve() if args.output else ROOT / ("TestProfiles-en-US" if LOCALE == "en-US" else "TestProfiles")
    if not args.check:
        existing = [v for v in VARIANTS if (OUTPUT / v).exists()]
        if existing:
            parser.error("Profile już istnieją; nie zostaną nadpisane: " + ", ".join(existing))
        OUTPUT.mkdir(exist_ok=True)
        for variant in VARIANTS:
            create_profile(variant)
        if LOCALE == "en-US":
            launcher = OUTPUT / "open.sh"
            launcher.write_text((ROOT / "TestProfiles/open.sh").read_text().replace(
                "runtime/thunderbird/thunderbird", "runtime/thunderbird-en-US/thunderbird"))
            launcher.chmod(0o755)
    check()
