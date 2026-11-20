#!/usr/bin/env python3
"""Control one real Logseq window; never close it or read its graph."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

PARKING = "special:omarchy-logseq"
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "omarchy-logseq"


def hypr(*args):
    result = subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=4)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def query(name):
    return json.loads(hypr("-j", name))


def lua(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # JSON's ordinary string escapes are also Lua string escapes here. Inputs
    # are compositor IDs/names, never window titles or note content.
    return json.dumps(str(value), ensure_ascii=False)


def dispatch(method, **kwargs):
    fields = ", ".join(f"{key} = {lua(value)}" for key, value in kwargs.items())
    # Focus and workspace moves can warp the pointer. Suppress warps for this
    # one synchronous compositor action, restoring the user's setting even on
    # failure. One Lua evaluation prevents other input events from observing
    # the temporary setting, and never moves the cursor back after the fact.
    result = hypr("eval", (
        'local old = hl.get_config("cursor.no_warps"); '
        'hl.config({ cursor = { no_warps = true } }); '
        'local ok, err = pcall(function() '
        f'hl.dispatch(hl.dsp.{method}({{ {fields} }})) '
        'end); '
        'hl.config({ cursor = { no_warps = old } }); '
        'if not ok then error(err) end'
    ))
    if result != "ok":
        raise RuntimeError(result)


def state_path():
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "current")
    return RUNTIME / (signature + ".json")


def read_state():
    try:
        return json.loads(state_path().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    path = state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(path)


def pick_client(clients, state):
    matches = [c for c in clients if c.get("mapped") and c.get("class", "").lower() == "logseq"]
    for client in matches:
        if client.get("stableId", client["address"]) == state.get("identity"):
            return client
    # Prefer the most recently focused Logseq window if multiple graphs exist.
    return min(matches, key=lambda c: c.get("focusHistoryID", 9999), default=None)


def is_managed(client, state):
    return bool(client and state.get("managed") and
                client.get("stableId", client["address"]) == state.get("identity"))


def visible(client, monitors):
    if not client or client.get("hidden"):
        return False
    return any(m["id"] == client["monitor"] and
               (client.get("pinned") or client["workspace"]["id"] in
                (m["activeWorkspace"]["id"], m["specialWorkspace"]["id"]))
               for m in monitors)


def status():
    state = read_state()
    client = pick_client(query("clients"), state)
    monitors = query("monitors")
    if not client:
        return {"running": False, "managed": False, "visible": False}
    monitor = next((m for m in monitors if m["id"] == client["monitor"]), None)
    managed = is_managed(client, state)
    active = query("activewindow")
    return {"running": True, "managed": managed, "visible": visible(client, monitors),
            "address": client["address"], "pid": client["pid"],
            "focused": active.get("address") == client["address"],
            "screen": monitor["name"] if monitor else "",
            "x": client["at"][0] - (monitor["x"] if monitor else 0),
            "y": client["at"][1] - (monitor["y"] if monitor else 0),
            "width": client["size"][0], "height": client["size"][1],
            "workspace": client["workspace"]["name"]}


def geometry(monitor, options):
    width, height = monitor["width"], monitor["height"]
    if monitor.get("transform", 0) % 2:
        width, height = height, width
    width, height = width / monitor["scale"], height / monitor["scale"]
    left, top, right, bottom = monitor.get("reserved", [0, 0, 0, 0])
    header = 32
    w = int(min(max(480, options.get("width", 1100)), width - left - right - 16))
    h = int(min(max(320, options.get("height", 780)), height - top - bottom - header - 16))
    anchor = options.get("anchorX", width / 2)
    x = int(max(left + 8, min(anchor - w / 2, width - right - w - 8)))
    y = int(top + 8 + header)
    return monitor["x"] + x, monitor["y"] + y, w, h


def act(action, options):
    state = read_state()
    client = pick_client(query("clients"), state)
    if not client:
        if action in ("hide", "detach", "restore"):
            return
        # Use the installed desktop entry, retaining its existing launch flags.
        subprocess.Popen(["gtk-launch", "logseq"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(100):
            time.sleep(0.2)
            client = pick_client(query("clients"), {})
            if client:
                break
        if not client:
            raise RuntimeError("Logseq did not open a window within 20 seconds.")
    monitors = query("monitors")
    monitor = next((m for m in monitors if m["name"] == options.get("screen")), None)
    monitor = monitor or next((m for m in monitors if m["focused"]), monitors[0])
    managed = is_managed(client, state)
    selector = "address:" + client["address"]
    if action == "toggle":
        action = "hide" if managed and visible(client, monitors) else "show"
    if action == "popout":
        action = "detach" if managed else "show"

    if action in ("detach", "restore"):
        if not managed:
            return
        original = state["original"]
        workspace = original["workspace"]["name"] if action == "restore" else monitor["activeWorkspace"]["name"]
        workspace = workspace if workspace.startswith("special:") else "name:" + workspace
        dispatch("window.move", window=selector, workspace=workspace, follow=False)
        dispatch("window.float", window=selector, action="on" if original["floating"] else "off")
        if original["floating"]:
            dispatch("window.resize", window=selector, x=original["size"][0], y=original["size"][1])
            if action == "restore":
                dispatch("window.move", window=selector, x=original["at"][0], y=original["at"][1])
        if original.get("pinned"):
            dispatch("window.pin", window=selector, action="on")
        if original.get("fullscreen") or original.get("fullscreenClient"):
            dispatch("window.fullscreen_state", window=selector, internal=original.get("fullscreen", 0),
                     client=original.get("fullscreenClient", 0))
        state["managed"] = False
        save_state(state)
        if action == "detach":
            dispatch("focus", window=selector)
        return

    if action == "hide":
        if managed:
            dispatch("window.move", window=selector, workspace=PARKING, follow=False)
            previous = state.get("previousFocus")
            if previous and any(c["address"] == previous and visible(c, monitors) for c in query("clients")):
                dispatch("focus", window="address:" + previous)
        return

    if not managed:
        if client.get("grouped"):
            raise RuntimeError("Move Logseq out of its window group before docking it.")
        state = {"managed": True, "identity": client.get("stableId", client["address"]),
                 "original": {k: client[k] for k in ("workspace", "floating", "size", "at", "pinned", "fullscreen", "fullscreenClient")}}
    active = query("activewindow")
    if active.get("address") != client["address"]:
        state["previousFocus"] = active.get("address")
    # Persist the original geometry before any compositor changes for recovery.
    save_state(state)
    if client.get("fullscreen") or client.get("fullscreenClient"):
        dispatch("window.fullscreen_state", window=selector, internal=0, client=0)
    if client.get("pinned"):
        dispatch("window.pin", window=selector, action="off")
    dispatch("window.float", window=selector, action="on")
    dispatch("window.move", window=selector, workspace="name:" + monitor["activeWorkspace"]["name"], follow=False)
    x, y, w, h = geometry(monitor, options)
    dispatch("window.resize", window=selector, x=w, y=h)
    dispatch("window.move", window=selector, x=x, y=y)
    dispatch("window.alter_zorder", window=selector, mode="top")
    dispatch("focus", window=selector)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "toggle", "show", "hide", "popout", "detach", "restore"))
    parser.add_argument("options", nargs="?", default="{}")
    args = parser.parse_args()
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    try:
        if args.action != "status":
            with (RUNTIME / "controller.lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                act(args.action, json.loads(args.options))
        print(json.dumps(status()))
    except Exception as error:
        print(json.dumps({"error": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
