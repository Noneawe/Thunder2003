# Generated demo profiles

Only this README and `open.sh` are tracked. The six profiles are generated
locally; they contain fictional mail and offline POP3/SMTP settings.

For English profiles:

```bash
python3 -B tools/create_test_profiles.py --locale en-US
python3 -B tools/create_test_profiles.py --locale en-US --check
bash tools/download_thunderbird.sh en-US
./TestProfiles-en-US/open.sh blue
```

For Polish profiles:

```bash
python3 -B tools/create_test_profiles.py
python3 -B tools/create_test_profiles.py --check
bash tools/download_thunderbird.sh pl
./TestProfiles/open.sh blue
```

Each profile contains 72 messages, 38 initially unread messages, 25 messages
with attachments and 16 replies. Addresses use reserved example domains;
servers point to `127.0.0.1:65534`, automatic checking is disabled and the
launcher starts Thunderbird offline. The generator refuses to overwrite
existing profiles. Do not commit generated profiles.

See the [testing instructions](../README.md#development-and-testing) for
real-window captures with Xvfb and a window manager.
