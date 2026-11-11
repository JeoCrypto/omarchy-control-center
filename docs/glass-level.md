# Glass level

`glass-level` sets how see-through the desktop is, from one command. It is optional: Control Center works without it and hides its Glass row.

```bash
glass-level              # print the current level
glass-level frosted      # clear | glass | frosted | solid
glass-level next         # step forwards; prev steps back
```

## Install

From the plugin folder:

```bash
cd ~/.config/omarchy/plugins/io.github.jeocrypto.control-center
install -Dm755 extras/glass-level ~/.local/bin/glass-level
install -Dm644 extras/glass.lua ~/.config/hypr/glass.lua
```

Add this line at the end of `~/.config/hypr/looknfeel.lua`:

```lua
dofile(os.getenv("HOME") .. "/.config/hypr/glass.lua")
```

Then run `glass-level glass`.

## What each level sets

| | `clear` | `glass` | `frosted` | `solid` |
|---|---|---|---|---|
| Bar background | 30% | 55% | 78% | 100% |
| Menus, popups, notifications | 72% | 90% | 95% | 100% |
| Launcher | 70% | 88% | 94% | 100% |
| Glass Dock | 32% | 55% | 78% | 100% |
| Blur | size 5, 2 passes | size 8, 3 passes | size 12, 4 passes | off |
| Terminals and file manager (focused / unfocused) | 93% / 88% | solid | solid | solid |

Percentages are how opaque the surface is.

## What it writes

`glass-level` changes three things and nothing else:

1. **`~/.config/glass/level`**: one word, the current level. [Glass Dock](https://github.com/JeoCrypto/omarchy-glass-dock) watches this file.
2. **A few keys in `~/.config/omarchy/shell.toml`**, each ending in `# glass-level`. This is Omarchy's own per-machine override file for shell surfaces, and the shell reloads it live. The keys set the background opacity of the bar, popups, notifications, menu and launcher, and their glass-edge borders. They are merged into the tables you already have: a `[bar]` of your own keeps its other settings and is not repeated. Anything else in the file, such as the `[font]` section that `omarchy display text size` writes, is left alone.
3. **It runs `hyprctl reload`**, so Hyprland runs `glass.lua` again.

**How the files are changed.** Each change is one transaction over `shell.toml` and the level file. One `glass-level` runs at a time (a lock in `~/.config/glass/.lock`). The new contents of `shell.toml` are checked to be valid and to differ from the old only in these keys, and the file is swapped into place in one step with its permissions kept. Then `~/.config/glass/level` is written the same way.

- If anything fails before `shell.toml` is swapped, nothing was changed and the command says why.
- If the level file cannot be written after that, `shell.toml` is put back as it was.
- A request to stop (Ctrl+C, `kill`) waits until both files are done.
- For the length of the change, the level being set is noted in `~/.config/glass/.pending`. If a run is killed outright between the two files, or cannot put `shell.toml` back, the note stays. The next run of `glass-level`, including the one that only prints the level, finishes the change: when `shell.toml` holds the noted level, the level file is set to it. Until then the two files can disagree.

A `shell.toml` that is a symlink stays a symlink. A block between `# glass-level: start` and `# glass-level: end` from version 1.0.1 or earlier is converted the first time you change the level.

`glass.lua` is read-only: it reads the level and the theme's accent colour, then sets blur, the opacity of windows Omarchy tags as see-through, a blur rule for the shell's layers, and gradient window borders. It overrides these Hyprland settings from wherever else you set them: `decoration.inactive_opacity`, `decoration.blur.enabled/size/passes`, and `general.col.active_border/inactive_border`.

## Things to know

- Unfocused windows are no longer slightly see-through; `inactive_opacity` is set to 1. If your theme dims inactive windows, that still applies.
- The window border colours come from `glass.lua`, not the theme's `hyprland.lua`. The focused border uses the theme's `accent`; the unfocused border is a faint white.
- The values are plain tables at the top of both files. Edit them to taste.
- `glass-level` is a Python 3 script (3.11 or newer, which Omarchy includes).

## Remove

1. Delete the `dofile(...)` line from `~/.config/hypr/looknfeel.lua`.
2. Delete the lines ending in `# glass-level` in `~/.config/omarchy/shell.toml`: `sed -i '/# glass-level$/d' ~/.config/omarchy/shell.toml`
3. Remove the files: `rm -r ~/.local/bin/glass-level ~/.config/hypr/glass.lua ~/.config/glass`

Run `hyprctl reload` afterwards.
