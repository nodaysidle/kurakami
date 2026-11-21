#!/bin/bash
# Links the launcher and desktop entry into ~/.local. Safe to re-run.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
ln -sf "$here/bin/kuraoke-kami" ~/.local/bin/kuraoke-kami
sed "s|^Exec=.*|Exec=$here/bin/kuraoke-kami|" "$here/kuraoke-kami.desktop" > ~/.local/share/applications/kuraoke-kami.desktop
cp "$here/kuraoke-kami.svg" ~/.local/share/icons/hicolor/scalable/apps/kuraoke-kami.svg
update-desktop-database ~/.local/share/applications 2>/dev/null || true
gtk-update-icon-cache -q ~/.local/share/icons/hicolor 2>/dev/null || true
# fish: `karaokeimp` = the song import tool (autoloaded from ~/.config/fish/functions)
mkdir -p ~/.config/fish/functions
cat > ~/.config/fish/functions/karaokeimp.fish <<FISH
function karaokeimp --description "Import downloaded songs into Kuraoke Kami (names, lyrics, folder)"
    python3 $here/tools/import_songs.py \$argv
end
FISH
cat > ~/.config/fish/functions/karaokelrc.fish <<FISH
function karaokelrc --description "Fetch missing timed lyrics for the Kuraoke Kami song folder"
    python3 $here/tools/fetch_lrc.py \$argv
end
FISH
cat > ~/.config/fish/functions/karaokedoctor.fish <<FISH
function karaokedoctor --description "Check Kuraoke Kami: tools, SoundFont, folders, recent errors"
    $here/bin/kuraoke-kami --doctor
end
FISH
# Omarchy menu: Apps -> Kuraoke Kami (added once to the user's menu extension, before its closing brace)
menu=~/.config/omarchy/extensions/omarchy-menu.jsonc
if [ -f "$menu" ] && ! grep -q '"apps.kuraoke-kami"' "$menu"; then
    python3 - "$menu" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
entry = ('\n  // Kuraoke Kami\n  "apps.kuraoke-kami": {\n    "icon": "\U000f0836",\n    "label": "Kuraoke Kami",\n'
         '    "description": "Offline home karaoke machine",\n    "aliases": ["karaoke", "kuraoke", "sing"],\n'
         '    "action": "uwsm-app -- gtk-launch kuraoke-kami.desktop"\n  }\n')
i = s.rstrip().rfind("}")
head = s[:i].rstrip()
if not head.endswith((",", "{")):
    head += ","
open(p, "w", encoding="utf-8").write(head + "\n" + entry + "}\n")
PY
    omarchy-menu refresh >/dev/null 2>&1 || true
    echo "Added to the Omarchy menu: Apps -> Kuraoke Kami"
fi
echo "Installed. Launch with: kuraoke-kami   (or from the app launcher)"
missing=""
for c in mpv ffmpeg ffprobe fluidsynth; do command -v $c >/dev/null || missing="$missing $c"; done
[ -n "$missing" ] && echo "Missing:$missing  ->  sudo pacman -S mpv ffmpeg fluidsynth"
compgen -G "/usr/share/soundfonts/*.sf[23]" >/dev/null || compgen -G "$HOME/.local/share/soundfonts/*.sf[23]" >/dev/null || echo "No SoundFont (needed for MIDI/KAR)  ->  sudo pacman -S soundfont-fluid"
exit 0
