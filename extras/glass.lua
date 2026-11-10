-- Glass level for Omarchy (Hyprland Lua config).
--
-- Load this from ~/.config/hypr/looknfeel.lua, after your own look'n'feel settings:
--
--   dofile(os.getenv("HOME") .. "/.config/hypr/glass.lua")
--
-- It reads the level written by the `glass-level` command
-- (~/.config/glass/level: clear | glass | frosted | solid) and sets:
--   * blur strength (off on "solid")
--   * window opacity: windows you read in (terminals, file manager) stay solid,
--     except on "clear"
--   * glass edges: window borders that are brightest along the top and fade
--     towards the bottom; the focused window keeps the theme's accent colour
--
-- `glass-level <level>` rewrites the level file and reloads Hyprland, which
-- runs this file again.

local home = os.getenv("HOME")

local function first_line(path)
  local f = io.open(path)
  if not f then return nil end
  local line = f:read("l")
  f:close()
  return line
end

local levels = {
  clear   = { blur = true,  size = 5,  passes = 2, windows = "0.93 0.88" },
  glass   = { blur = true,  size = 8,  passes = 3, windows = "1.0 1.0" },
  frosted = { blur = true,  size = 12, passes = 4, windows = "1.0 1.0" },
  solid   = { blur = false, size = 8,  passes = 3, windows = "1.0 1.0" },
}
local level = levels[first_line(home .. "/.config/glass/level") or "glass"] or levels.glass

hl.config({
  decoration = {
    inactive_opacity = 1.0,
    blur = { enabled = level.blur, size = level.size, passes = level.passes },
  },
})

-- Omarchy tags its see-through windows (terminals, file manager) with
-- "transparent-window"; this sets how solid they are at the current level.
o.window({ tag = "transparent-window" }, { opacity = level.windows })

-- Frost the shell surfaces so the level is visible on the bar, menus and dock.
hl.layer_rule({
  match = { namespace = "^(omarchy-bar|omarchy-menu|omarchy-notifications|glass-dock)$" },
  blur = true,
  ignore_alpha = 0.2,
})

-- Glass edges, in the active theme's accent colour.
local accent = "e8743b"
do
  local f = io.open(home .. "/.local/state/omarchy/current/theme/colors.toml")
  if f then
    accent = ("\n" .. f:read("a")):match('\naccent%s*=%s*"#(%x%x%x%x%x%x)"') or accent
    f:close()
  end
end

hl.config({
  general = {
    col = {
      active_border = { colors = { "rgba(" .. accent .. "ff)", "rgba(" .. accent .. "66)" }, angle = 90 },
      inactive_border = { colors = { "rgba(ffffff40)", "rgba(ffffff0a)" }, angle = 90 },
    },
  },
})
