# SPDX-License-Identifier: GPL-3.0-or-later
"""User-facing error pipeline: record -> popup -> Copy Report.

Every failure in an AquaSuite operator, property-update callback or frame
handler goes through ``record``.  Each distinct error is shown once per
Blender session in a popup with a plain-language message and a Copy Report
button.  Operators show it immediately; update callbacks and handlers
cannot open dialogs, so their errors are shown by a timer — never while an
animation plays or a render runs.  The report is scrubbed of the user's
home folder and the .blend path/name, because buyers paste it into public
issues.
"""

import functools
import os
import platform
import re
import traceback

import bpy

from .. import constants as C

_pending = []      # errors waiting to be shown
_seen = set()      # error keys already queued this session
_last = None       # most recent error, for Copy Report
_TIMER_DELAY = 0.3


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def plain_message(exc):
    """A sentence for the user.  RuntimeError messages are written for
    users by AquaSuite or Blender; anything else is an internal fault."""
    if isinstance(exc, RuntimeError):
        msg = str(exc).strip()
        msg = re.sub(r"^Error:\s*", "", msg).strip()
        if msg:
            return msg[0].upper() + msg[1:]
    return "Something unexpected went wrong inside AquaSuite."


def record(title, exc=None, message=None, mode="", uuid="", tb=None):
    """Store an error; queue it for a popup unless already shown this
    session.  Returns the error record."""
    global _last
    if tb is None:
        tb = traceback.format_exc() if exc is not None else ""
        if tb.strip() == "NoneType: None":
            tb = ""
    err = {
        "title": title,
        "message": message or (plain_message(exc) if exc is not None else ""),
        "mode": mode,
        "uuid": uuid,
        "exception": f"{type(exc).__name__}: {exc}" if exc is not None else "",
        "traceback": tb,
    }
    err["key"] = (title, err["exception"].split("\n")[0][:200], uuid)
    _last = err
    print(f"[AquaSuite] {title}: {err['message']} {err['exception']}")
    if err["key"] not in _seen:
        _seen.add(err["key"])
        _pending.append(err)
    return err


def pending():
    return list(_pending)


def last_error():
    return _last


def reset_session():
    """Forget everything (tests, add-on reload)."""
    global _last
    _pending.clear()
    _seen.clear()
    _last = None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _variants(path):
    if not path:
        return []
    out = {path, path.replace("\\", "/"), path.replace("/", "\\")}
    return sorted((p for p in out if len(p) > 3), key=len, reverse=True)


def scrub(text):
    """Remove the .blend path/name and the user's home folder."""
    if not text:
        return text
    blend = bpy.data.filepath
    subs = []
    if blend:
        subs += [(v, "<blend-file>") for v in _variants(blend)]
        subs += [(v, "<blend-folder>") for v in _variants(os.path.dirname(blend))]
        name = os.path.splitext(os.path.basename(blend))[0]
        if len(name) > 2:
            subs.append((name, "<blend-name>"))
    subs += [(v, "<home>") for v in _variants(os.path.expanduser("~"))]
    for old, new in subs:
        text = re.sub(re.escape(old), lambda _m: new, text, flags=re.IGNORECASE)
    # Any other user folder that slipped through (other drive letters, temp).
    text = re.sub(r"([A-Za-z]:[\\/]Users[\\/])[^\\/\s]+", r"\1<user>", text)
    text = re.sub(r"(/(?:home|Users)/)[^/\s]+", r"\1<user>", text)
    return text


def build_report(err):
    data_version = ""
    if err.get("uuid"):
        try:
            from . import registry
            e = registry.get(bpy.context.scene, err["uuid"])
            if e is not None:
                data_version = f"{e.data_version} (made with {e.addon_version or 'unknown'})"
        except Exception:
            pass
    lines = [
        "AquaSuite bug report",
        f"Add-on version: {C.ADDON_VERSION}",
        f"Blender: {bpy.app.version_string}",
        f"OS: {platform.platform()}",
        f"Mode: {C.MODE_LABELS.get(err.get('mode'), err.get('mode') or '-')}",
        f"Setup data version: {data_version or '-'}",
        f"What happened: {err['title']} — {err['message']}",
    ]
    if err.get("exception"):
        lines.append(f"Error: {err['exception']}")
    if err.get("traceback"):
        lines += ["Traceback:", err["traceback"].rstrip()]
    return scrub("\n".join(lines))


# ---------------------------------------------------------------------------
# Showing
# ---------------------------------------------------------------------------

def _busy():
    """Playback or a render job: never interrupt with a popup."""
    try:
        if bpy.app.is_job_running("RENDER"):
            return True
    except Exception:
        pass
    wm = bpy.context.window_manager
    for win in getattr(wm, "windows", []):
        if win.screen is not None and getattr(win.screen, "is_animation_playing", False):
            return True
    return False


def _draw_popup(err):
    def draw(menu, _context):
        layout = menu.layout
        if err["message"]:
            layout.label(text=err["message"])
        layout.label(text="Copy the report and paste it in a new issue at:")
        layout.label(text=C.SUPPORT_URL)
        layout.operator("aquasuite.copy_report", icon="COPYDOWN")
    return draw


def _show(err):
    # Headless Blender (render farms, `blender -b`) still reports a window,
    # and opening a popup there crashes Blender: never show UI headless.
    if bpy.app.background:
        return False
    wm = bpy.context.window_manager
    windows = list(getattr(wm, "windows", []))
    if not windows:
        return False
    try:
        with bpy.context.temp_override(window=windows[0]):
            bpy.context.window_manager.popup_menu(
                _draw_popup(err), title=err["title"], icon="ERROR")
        return True
    except Exception as exc:
        print(f"[AquaSuite] could not open error popup: {exc}")
        return False


def show_pending():
    """Show the oldest pending error now, if possible.  True if shown."""
    if not _pending or _busy():
        return False
    if _show(_pending[0]):
        _pending.pop(0)
        return True
    return False


def _timer():
    if not _pending or bpy.app.background:
        return None
    if _busy() or not getattr(bpy.context.window_manager, "windows", None):
        return 1.0                          # try again when idle
    show_pending()
    return _TIMER_DELAY if _pending else None


def schedule():
    if bpy.app.background:
        return
    if not bpy.app.timers.is_registered(_timer):
        bpy.app.timers.register(_timer, first_interval=_TIMER_DELAY)


def unschedule():
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def fail(op, title, exc=None, message=None, mode="", uuid=""):
    """For operators: record, show the popup now, put the message in the
    status bar.  Returns {"CANCELLED"}."""
    err = record(title, exc, message=message, mode=mode, uuid=uuid)
    try:
        op.report({"ERROR"}, f"{title}: {err['message']}")
    except Exception:
        pass
    if not show_pending():
        schedule()
    return {"CANCELLED"}


def _operator_title(op):
    label = getattr(op, "bl_label", "") or "do that"
    return f"AquaSuite couldn't {label[0].lower() + label[1:]}"


def guard_operator(execute):
    """Wrap an operator's execute so no failure escapes to the user as a
    Python traceback."""
    if getattr(execute, "_aqs_guarded", False):
        return execute

    @functools.wraps(execute)
    def wrapper(self, context):
        try:
            return execute(self, context)
        except Exception as exc:
            entry_uuid = getattr(self, "uuid", "") or ""
            mode = ""
            if entry_uuid:
                from . import registry
                e = registry.get(context.scene, entry_uuid)
                mode = e.mode if e is not None else ""
            return fail(self, _operator_title(self), exc, mode=mode, uuid=entry_uuid)
    wrapper._aqs_guarded = True
    return wrapper


def guard_update(title):
    """Wrap a property-update callback: record failures (shown later by
    the timer) instead of raising into Blender's UI code."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(self, context):
            try:
                return fn(self, context)
            except Exception as exc:
                record(title, exc, mode=getattr(self, "mode", "") or "",
                       uuid=getattr(self, "uuid", "") or "")
                schedule()
        return wrapper
    return deco


class AQS_OT_copy_report(bpy.types.Operator):
    bl_idname = "aquasuite.copy_report"
    bl_label = "Copy Report"
    bl_description = ("Copy a bug report (versions, what happened, technical "
                      "details — personal paths removed) to paste into a "
                      "new issue")

    def execute(self, context):
        err = last_error()
        if err is None:
            self.report({"INFO"}, "No AquaSuite error to report")
            return {"CANCELLED"}
        text = build_report(err)
        try:
            context.window_manager.clipboard = text
            self.report({"INFO"}, f"Report copied — paste it at {C.SUPPORT_URL}")
        except Exception:
            print(text)
            self.report({"WARNING"}, "Couldn't use the clipboard — the report "
                                     "was printed to the system console")
        return {"FINISHED"}


CLASSES = (AQS_OT_copy_report,)


def register():
    reset_session()


def unregister():
    unschedule()
