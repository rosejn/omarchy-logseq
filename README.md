# Logseq bar window

## Install

```bash
omarchy plugin add https://github.com/rosejn/omarchy-logseq.git --enable
```

An Omarchy bar widget controlling the installed Logseq desktop app. It does not
read notes, change the graph, or rebuild Logseq's interface.

- Click the Logseq icon to show a floating window beneath the bar.
- Click again, or press the companion strip's **−**, to park the same running
  window in `special:omarchy-logseq`.
- Press **↗** to return the window to normal desktop use. Its previous tiled or
  floating mode is restored on the current workspace.
- Right-click the bar icon to pop out/dock. Clicking a detached window's bar icon
  docks it again.
- Launches through the existing `logseq.desktop` entry only if no Logseq window
  exists. When several exist, manages one, preferring the most recently focused.

The narrow controls strip is a separate shell surface above Logseq; it appears
while the docked Logseq window has focus. Showing and hiding never closes Logseq.
The ordinary application close command still closes it normally.
Window actions preserve the pointer position while still setting keyboard
focus. Cursor warping is suppressed only during each synchronous compositor
action; the desktop's existing cursor setting is restored immediately.

Designed for a top bar. Width and height default to 1100 × 780 logical pixels
and are clamped to the monitor's available area. Change through bar settings or:

    omarchy bar set rosejn.logseq width 1200 --json
    omarchy bar set rosejn.logseq height 850 --json

## Recovery / removal

Before removing the widget, pop it out, or run:

    python3 ~/.config/omarchy/plugins/rosejn.logseq/controller.py restore

This restores the original workspace and tiled/floating state without closing
Logseq. Then remove the widget through Omarchy's plugin/bar settings. The plugin
does not install a service, keybinding, or permanent Hyprland window rule.

State is saved under `$XDG_RUNTIME_DIR/omarchy-logseq/`, scoped to the Hyprland
session, so shell hot reloads retain the window identity and original geometry.
Requires the existing Python 3, Hyprland 0.55+ Lua dispatchers, and `gtk-launch`.
