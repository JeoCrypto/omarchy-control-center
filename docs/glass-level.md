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
2. **A marked block in `~/.config/omarchy/shell.toml`**, between `# glass-level: start` and `# glass-level: end`. This is Omarchy's own per-machine override file for shell surfaces, and the shell reloads it live. The block sets the background opacity of the bar, popups, notifications, menu and launcher, and their glass-edge borders. Anything else in the file, such as the `[font]` section that `omarchy display text size` writes, is left alone.
3. **It runs `hyprctl reload`**, so Hyprland runs `glass.lua` again.

`glass.lua` is read-only: it reads the level and the theme's accent colour, then sets blur, the opacity of windows Omarchy tags as see-through, a blur rule for the shell's layers, and gradient window borders. It overrides these Hyprland settings from wherever else you set them: `decoration.inactive_opacity`, `decoration.blur.enabled/size/passes`, and `general.col.active_border/inactive_border`.

## Things to know

- Unfocused windows are no longer slightly see-through; `inactive_opacity` is set to 1. If your theme dims inactive windows, that still applies.
- The window border colours come from `glass.lua`, not the theme's `hyprland.lua`. The focused border uses the theme's `accent`; the unfocused border is a faint white.
- The values are plain tables at the top of both files. Edit them to taste.

## Remove

1. Delete the `dofile(...)` line from `~/.config/hypr/looknfeel.lua`.
2. Delete the block between `# glass-level: start` and `# glass-level: end` in `~/.config/omarchy/shell.toml`.
3. Remove the files: `rm ~/.local/bin/glass-level ~/.config/hypr/glass.lua ~/.config/glass/level`

Run `hyprctl reload` afterwards.
