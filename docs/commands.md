# Commands and settings

Control Center's panel is a view over one script, `bin/control-center`, inside the plugin folder. Anything the panel does can also be run from a terminal, a keybinding or another script.

```bash
cc=~/.config/omarchy/plugins/io.github.jeocrypto.control-center/bin/control-center
```

## The backend

| Command | What it does |
|---|---|
| `$cc status` | Prints one line of JSON with the state of every control |
| `$cc wifi` | Switches Wi-Fi on or off (`nmcli radio wifi`) |
| `$cc bluetooth` | Switches Bluetooth on or off (`omarchy-bluetooth-power toggle`) |
| `$cc dnd` | Toggles Do Not Disturb (`omarchy-toggle-notification-silencing`) |
| `$cc nightlight` | Toggles Night Light (`omarchy-toggle-nightlight`) |
| `$cc awake` | Toggles Stay Awake (`omarchy-toggle-idle toggle`) |
| `$cc mute` | Mutes or unmutes the default output (`wpctl set-mute`) |
| `$cc brightness <0-100>` | Sets display brightness (`omarchy-brightness-display`) |
| `$cc volume <0-100>` | Sets the default output's volume (`wpctl set-volume`) |
| `$cc glass <level>` | Sets the glass level; needs [`glass-level`](glass-level.md) |

`status` looks like this:

```json
{"wifi":true,"ssid":"Home","bluetooth":true,"dnd":false,"nightlight":false,"awake":false,"brightness":50,"volume":30,"muted":false,"glass":"glass"}
```

`brightness` is `null` when there is no controllable backlight, and `glass` is `""` when `glass-level` isn't installed. The panel hides those two rows in that case.

## The panel

| Command | What it does |
|---|---|
| `omarchy-shell shell toggle io.github.jeocrypto.control-center` | Opens or closes the panel |
| `omarchy-shell shell summon io.github.jeocrypto.control-center` | Opens it |
| `omarchy-shell shell hide io.github.jeocrypto.control-center` | Closes it |
| `omarchy-shell io.github.jeocrypto.control-center refresh` | Re-reads every control now |

While the panel is open it re-reads the state every 2.5 seconds, so a change made elsewhere (a hardware key, another panel) shows up on its own. Call `refresh` after a script changes something if you want it to show at once.

## Settings

Settings live in the widget's entry in `~/.config/omarchy/shell.json` and are set with `omarchy bar set`.

| Setting | Default | What it does |
|---|---|---|
| `showNetworkName` | `true` | `false` shows "Connected" on the Wi-Fi tile instead of the network's name |

```bash
omarchy bar set io.github.jeocrypto.control-center showNetworkName false
```

## Colours

The tints for switched-on controls come from the active theme's `colors.toml`: `blue` (Wi-Fi, Bluetooth), `magenta` (Do Not Disturb), `yellow` (Night Light) and `green` (Stay Awake). They follow a theme change. A theme without those keys gets the Golden Gate values.

## Translations

Strings are in `i18n/<language>.json`, one flat JSON file per Omarchy language code. `en.json` is the reference. To add a language, copy it, translate the values and keep the keys. A missing string falls back to the base language, then to English.
