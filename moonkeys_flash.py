"""Compile + flash the Moonlander firmware.

`make compile` and `make flash` run inside ~/montressor/moonlander. Flashing is
gated: it never runs without the user explicitly confirming and being present at
the board to push the reset pinhole. The flash command reuses the exact
DFU-watcher block from ~/avengers/claude/skills/moonlander-hotkey.md §E.

Both long-running commands are launched in a visible kitty terminal so the user
sees live output and the "push reset" prompt, and the GTK popup stays responsive.
"""
import os
import subprocess
import tempfile

MOONLANDER_DIR = os.path.expanduser('~/montressor/moonlander')

# Verbatim from moonlander-hotkey.md §E — USB watcher in background, qmk flash
# poller in foreground, filtering webcam/Bluetooth devices that incidentally
# claim DFU descriptors.
_FLASH_BLOCK = r'''
( for i in $(seq 1 90); do
    if lsusb | grep -q "0483:df11"; then
      echo "=== BOOTLOADER DETECTED at $(date +%T) ==="
      break
    fi
    sleep 1
  done ) > /tmp/dfu-watch.log 2>&1 &
WATCHER=$!
cd ~/montressor/moonlander && timeout 120 make flash 2>&1 \
  | grep -vE "Cannot open DFU device 05c8|Cannot open DFU device 046d|Cannot open DFU device 8087" \
  | tail -25
echo "=== USB WATCHER ==="
cat /tmp/dfu-watch.log
kill $WATCHER 2>/dev/null
echo "=== POST-FLASH STATE ==="
lsusb | grep -E "3297|0483"
'''


def git_commit(message):
    """Commit keymap.c changes in the moonlander repo. Returns (ok, output)."""
    try:
        subprocess.run(['git', '-C', MOONLANDER_DIR, 'add', '-A'],
                       check=True, capture_output=True, text=True)
        r = subprocess.run(
            ['git', '-C', MOONLANDER_DIR, 'commit', '-m', message],
            capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.CalledProcessError as e:
        return False, (e.stdout or '') + (e.stderr or '')


def _run_in_kitty(script_body, title):
    """Write a script to a temp file and run it in a held kitty window."""
    fd, path = tempfile.mkstemp(prefix='moonkeys-', suffix='.sh')
    with os.fdopen(fd, 'w') as f:
        f.write('#!/usr/bin/env bash\nset -uo pipefail\n')
        f.write(script_body)
        f.write('\necho; echo "[press any key to close]"; read -n1\n')
    os.chmod(path, 0o755)
    subprocess.Popen(['kitty', '--title', title, '--hold', 'bash', path])


def compile_only():
    _run_in_kitty('cd ~/montressor/moonlander && make compile\n',
                  'moonkeys · compile')


def compile_and_flash():
    _run_in_kitty(
        'cd ~/montressor/moonlander && make compile || exit 1\n'
        'echo; echo ">>> Push the reset pinhole on the bottom of the right half "\n'
        'echo ">>> (just left of the USB-C port), one firm second with a paperclip."\n'
        'echo ">>> Both top LEDs turn red = DFU mode. Flashing follows automatically."\n'
        + _FLASH_BLOCK,
        'moonkeys · compile + flash')
