# Contributor and agent guide

## Project purpose

Thunderbird 2003 is a set of six Thunderbird appearance customizations inspired
by Microsoft Outlook 2003, Office 2003 and Windows XP Luna. It combines native
colour-theme XPIs, custom CSS and original SVG action icons. Read README.md
for installation, screenshots and the compatibility boundaries.

## Design constraints

- Keep the six palettes coherent: Blue, Silver, Graphite, Mocha, Sage and Aurora.
- Preserve native mail commands, accessible button names, keyboard operation
  and dynamic states such as IMAP message restoration.
- The received-message preview subject is 16 px. The compose Subject field
  uses the regular surface and size, matching the sender field; there is no
  separate subject tint or reduced compose-subject font in the current design.
- Apply editor-surface colours through CSS scoped to `about:blank?compose`.
  Do not serialize theme colours into outgoing message HTML.
- Scope action-button SVG replacements to their intended toolbars. Do not
  inadvertently replace folder-tree icons or native window controls.
- Account settings currently use substantial native Thunderbird styling.
  Do not describe them as fully themed without implementing and testing it.

## Source files and generated output

Edit these sources:

- `Theme/gen/userChrome.template.css`: application UI styles.
- `Theme/gen/userContent.template.css`: message typography and compose styling.
- `Theme/gen/palettes.py`: colours for all six variants.
- `Theme/gen/icons/`: original SVG icons and `buttons.css` mappings.

Run `python3 -B Theme/gen/build.py` from the repository root after source
changes. Include the generated changes under all affected `Theme/<variant>/`
directories. Avoid hand-editing generated stylesheets in only one variant.

Keep existing theme IDs and manifest attribution unless the task explicitly
requires a metadata change. The builder reads the existing Blue XPI as its
base manifest; do not remove that build input.

`tools/create_test_profiles.py` generates disposable offline demo profiles.
`tools/demo_content_en.py` supplies English message fixtures.
`tools/capture_test_profiles.py` drives real Thunderbird windows through
Marionette. `TestProfiles/open.sh` is a tracked launcher; the profiles beside
it are generated files.

## Validation

Run the relevant offline checks after changing the build or test tools:

```bash
python3 -B tools/test_capture_test_profiles.py
python3 -B tools/test_english_mail.py
```

For theme changes:

1. Rebuild all affected variants and inspect the reported contrast checks.
2. Generate fresh profiles; the generator deliberately refuses to overwrite
   existing profiles. Use `--output TestProfiles-en-US-next` when necessary.
3. Validate them with the same locale and output directory using `--check`.
4. Run graphical captures with Xvfb **and a window manager**. The harness can
   start a system Openbox automatically. A bare Xvfb session does not provide
   a representative compose-window title bar.
5. Inspect actual screenshots, including light and dark palettes, the compose
   window, button states and any view touched by the change. Passing scripted
   assertions alone is not a visual review.

A typical English capture command is:

```bash
xvfb-run -a -s '-screen 0 1440x1000x24 -nolisten tcp' \
  python3 -B tools/capture_test_profiles.py --locale en-US \
  --profiles TestProfiles-en-US-next --output artifacts/gui-next
```

Use a new capture output directory for each run. The harness uses disposable
copies and sets `MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1` only for its test process,
as required by Thunderbird 159. Keep Thunderbird's sandbox and other security
features enabled.

Report which platforms, locales and dimensions were actually tested. Linux
screenshots do not establish Windows or macOS rendering compatibility.

## Repository hygiene

- Keep downloaded application binaries, window-manager packages, generated
  profiles, caches and full capture directories out of Git.
- Keep selected documentation screenshots limited to fictional test mail.
  Do not add personal mail, credentials or machine-specific profile settings.
- Keep README installation steps aligned with the packaged files. Users need
  the XPI, both CSS files and the complete icons folder from one variant.
- Use English for public documentation. `AGENDS.md` is a compatibility pointer
  to this file; keep the substantive instructions here.
- Prefer the Python standard library and existing tools over new dependencies.
- Do not publish or push to a remote merely to validate a local change.
