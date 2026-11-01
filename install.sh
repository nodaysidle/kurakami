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
echo "Installed. Launch with: kuraoke-kami   (or from the app launcher)"
missing=""
for c in mpv ffmpeg ffprobe fluidsynth; do command -v $c >/dev/null || missing="$missing $c"; done
[ -n "$missing" ] && echo "Missing:$missing  ->  sudo pacman -S mpv ffmpeg fluidsynth"
compgen -G "/usr/share/soundfonts/*.sf[23]" >/dev/null || compgen -G "$HOME/.local/share/soundfonts/*.sf[23]" >/dev/null || echo "No SoundFont (needed for MIDI/KAR)  ->  sudo pacman -S soundfont-fluid"
command -v qrencode >/dev/null || echo "Optional QR code on the TV  ->  sudo pacman -S qrencode"
exit 0
