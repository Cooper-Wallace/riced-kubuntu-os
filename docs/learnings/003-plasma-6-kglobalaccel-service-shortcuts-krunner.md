# 003 - KDE Plasma 6 KGlobalAccel Service Shortcuts and KRunner Binding

- **Date**: 2026-09-08
- **Target Component**: Plasma 6 / KGlobalAccel / KWin / KRunner
- **Environment**: Kubuntu 26.04 LTS (Plasma 6.6.6, Wayland)

---

### 1. Problem / Context
The `Meta+Space` shortcut (and `Alt+Space`) stopped activating KRunner on KDE Plasma 6. Pressing the shortcut had no visible effect, even though `Meta+Space` was defined in `kglobalshortcutsrc`.

### 2. Root Cause Analysis
1. **Plasma 5 vs Plasma 6 Configuration Namespace Drift**:
   In KDE Plasma 5, `.desktop` application shortcuts in `~/.config/kglobalshortcutsrc` were serialized under flat section names with dots converted to underscores (e.g. `[org_kde_krunner_desktop]`). In KDE Plasma 6 (KF6 / KWin on Wayland), desktop service shortcuts are scoped under nested subsections: `[services][org.kde.krunner.desktop]`.
2. **Ghost Component Collision in KGlobalAccel**:
   When `[org_kde_krunner_desktop]` was defined in `kglobalshortcutsrc`, KWin registered an orphaned component named `org_kde_krunner_desktop`. This component had no active client listener (`isActive == false`) and no matching service desktop file (`/usr/share/kglobalaccel/org.kde.krunner.desktop` uses dots). KGlobalAccel bound `Meta+Space` and `Alt+Space` to the ghost component, intercepting the keystrokes without forwarding them to KRunner or activating its DBus service. Meanwhile, the genuine `[services][org.kde.krunner.desktop]` entry had its primary key cleared to avoid key conflicts.

### 3. Solution / Applied Fix
1. Removed the orphaned component from KWin's running memory via DBus (`cleanUp()`).
2. Updated the KGlobalAccel shortcut registration on the legitimate `org.kde.krunner.desktop` service action `_launch` via `setForeignShortcutKeys` over DBus (`Meta+Space`, `Alt+Space`, and `Alt+F2`).
3. Replaced `[org_kde_krunner_desktop]` with `[services][org.kde.krunner.desktop]` in `plasma/configs/kglobalshortcutsrc`.
4. Verified that `plasma-krunner.service` is active and responsive to DBus activation.

```bash
# DBus update via python dbus
python3 -c "
import dbus
bus = dbus.SessionBus()
kga = bus.get_object('org.kde.kglobalaccel', '/kglobalaccel')
iface = dbus.Interface(kga, 'org.kde.KGlobalAccel')
actionId = ['org.kde.krunner.desktop', '_launch', 'KRunner', 'KRunner']
keys = [
    (dbus.Array([dbus.Int32(268435488), dbus.Int32(0), dbus.Int32(0), dbus.Int32(0)], signature='i'),), # Meta+Space
    (dbus.Array([dbus.Int32(134217760), dbus.Int32(0), dbus.Int32(0), dbus.Int32(0)], signature='i'),), # Alt+Space
    (dbus.Array([dbus.Int32(150994993), dbus.Int32(0), dbus.Int32(0), dbus.Int32(0)], signature='i'),), # Alt+F2
]
iface.setForeignShortcutKeys(actionId, keys)
"
```

### 4. Replication Impact
- Running `plasma/restore-kde.sh` safely restores `[services][org.kde.krunner.desktop]` without injecting legacy Plasma 5 section headers.
- System replication on clean Kubuntu 26.04 machines will immediately bind `Meta+Space` to KRunner without ghost component conflicts.
