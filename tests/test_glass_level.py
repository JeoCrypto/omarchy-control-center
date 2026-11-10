"""extras/glass-level: shell.toml is merged, checked and swapped in one step."""
import fcntl
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'extras/glass-level'
loader = importlib.machinery.SourceFileLoader('glass_level', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
g = importlib.util.module_from_spec(spec)
loader.exec_module(g)

LEGACY_BLOCK = '''# glass-level: start (managed by ~/.local/bin/glass-level; edits here are overwritten)
[bar]
background-alpha = 0.55

[popups]
background-alpha = 0.90
border = "rgba(ffffff5c) rgba(ffffff12) 90deg"
border-alpha = 1.0
# glass-level: end
'''


class Home:
    """A throwaway home folder with stand-ins for hyprctl and notify-send."""

    def __init__(self, case):
        self.dir = tempfile.TemporaryDirectory()
        case.addCleanup(self.dir.cleanup)
        self.home = Path(self.dir.name)
        self.toml = self.home / '.config/omarchy/shell.toml'
        self.level = self.home / '.config/glass/level'
        self.toml.parent.mkdir(parents=True)
        self.level.parent.mkdir(parents=True)
        bin_dir = self.home / 'bin'
        bin_dir.mkdir()
        for name in ('hyprctl', 'notify-send'):
            (bin_dir / name).write_text('#!/bin/sh\nexit 0\n')
            (bin_dir / name).chmod(0o755)
        self.env = {'HOME': str(self.home), 'PATH': f'{bin_dir}:/usr/bin:/bin'}

    def run(self, *args):
        with patch.dict(os.environ, self.env), patch('sys.stdout'), patch('sys.stderr'):
            return g.main(['glass-level', *args])

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def leftovers(self):
        return [p.name for folder in (self.toml.parent, self.level.parent)
                for p in folder.iterdir() if p.name.startswith(g.TEMP_PREFIX)]


class GlassLevelTests(unittest.TestCase):
    def setUp(self):
        self.h = Home(self)

    def test_new_file_gets_every_table_once(self):
        self.assertEqual(self.h.run('frosted'), 0)
        data = tomllib.loads(self.h.toml.read_text())
        self.assertEqual(data['bar'], {'background-alpha': 0.78})
        self.assertEqual(data['launcher']['background-alpha'], 0.94)
        self.assertEqual(data['tooltip']['border-alpha'], 1.0)
        self.assertEqual(self.h.level.read_text(), 'frosted\n')
        self.assertEqual(self.h.leftovers(), [])

    def test_existing_tables_are_merged_not_repeated(self):
        self.h.toml.write_text('[font]\nsize = 12  # mine\n\n[bar]\nposition = "top"\nbackground-alpha = 0.9\n\n'
                               '[menu]\nwidth = 320\n')
        self.assertEqual(self.h.run('clear'), 0)
        text = self.h.toml.read_text()
        data = tomllib.loads(text)   # duplicate tables would not parse
        self.assertEqual(text.count('[bar]'), 1)
        self.assertEqual(text.count('[menu]'), 1)
        self.assertEqual(data['bar'], {'position': 'top', 'background-alpha': 0.30})
        self.assertEqual(data['menu']['width'], 320)
        self.assertEqual(data['menu']['background-alpha'], 0.72)
        self.assertEqual(data['font'], {'size': 12})
        self.assertIn('size = 12  # mine', text)

    def test_block_from_earlier_versions_is_migrated(self):
        # The old block next to a [bar] of the user's own: two [bar] tables.
        self.h.toml.write_text('[font]\nsize = 12\n\n[bar]\nposition = "top"\n\n' + LEGACY_BLOCK)
        self.assertEqual(self.h.run('solid'), 0)
        text = self.h.toml.read_text()
        data = tomllib.loads(text)
        self.assertNotIn('glass-level: start', text)
        self.assertEqual(text.count('[bar]'), 1)
        self.assertEqual(data['bar'], {'position': 'top', 'background-alpha': 1.0})
        self.assertEqual(data['font'], {'size': 12})

    def test_changing_level_twice_is_stable(self):
        self.h.toml.write_text('[bar]\nposition = "top"\n')
        self.h.run('glass')
        first = self.h.toml.read_text()
        self.h.run('solid')
        self.h.run('glass')
        self.assertEqual(self.h.toml.read_text(), first)

    def test_invalid_file_is_left_alone(self):
        for broken in ('[bar\nx = 1\n', 'bar = { position = "top" }\n', '[bar]\nx = 1\n[bar]\ny = 2\n'):
            with self.subTest(broken=broken):
                self.h.toml.write_text(broken)
                self.h.level.write_text('glass\n')
                self.assertEqual(self.h.run('solid'), 1)
                self.assertEqual(self.h.toml.read_text(), broken)
                self.assertEqual(self.h.level.read_text(), 'glass\n')
                self.assertEqual(self.h.leftovers(), [])

    def test_interrupted_update_changes_nothing(self):
        original = '[font]\nsize = 12\n'
        self.h.toml.write_text(original)
        self.h.level.write_text('glass\n')
        with patch.object(g.os, 'replace', side_effect=OSError('interrupted')):
            self.assertEqual(self.h.run('solid'), 1)
        self.assertEqual(self.h.toml.read_text(), original)
        self.assertEqual(self.h.level.read_text(), 'glass\n')
        self.assertEqual(self.h.leftovers(), [])

    def test_killed_run_leaves_the_file_whole_and_is_cleaned_up(self):
        original = '[font]\nsize = 12\n'
        self.h.toml.write_text(original)
        # What a run killed between writing and swapping leaves behind.
        stale = self.h.toml.parent / (g.TEMP_PREFIX + 'killed')
        stale.write_text('[bar]\nbackground-al')
        self.assertEqual(tomllib.loads(self.h.toml.read_text()), {'font': {'size': 12}})
        self.assertEqual(self.h.run('glass'), 0)
        self.assertFalse(stale.exists())
        self.assertEqual(tomllib.loads(self.h.toml.read_text())['font'], {'size': 12})

    def test_level_file_is_not_written_when_the_update_fails(self):
        self.h.toml.write_text('[bar\n')
        self.assertEqual(self.h.run('frosted'), 1)
        self.assertFalse(self.h.level.exists())

    def test_change_made_meanwhile_is_kept(self):
        self.h.toml.write_text('[font]\nsize = 12\n')
        real = g.write_temp
        calls = []

        def meddle(folder, text, mode):
            if not calls and Path(folder) == self.h.toml.parent:
                calls.append(1)
                self.h.toml.write_text('[font]\nsize = 16\n')
            return real(folder, text, mode)

        with patch.object(g, 'write_temp', side_effect=meddle):
            self.assertEqual(self.h.run('glass'), 0)
        data = tomllib.loads(self.h.toml.read_text())
        self.assertEqual(data['font'], {'size': 16})
        self.assertEqual(data['bar'], {'background-alpha': 0.55})
        self.assertEqual(self.h.leftovers(), [])

    def test_permissions_are_kept(self):
        self.h.toml.write_text('[font]\nsize = 12\n')
        self.h.toml.chmod(0o600)
        self.assertEqual(self.h.run('glass'), 0)
        self.assertEqual(stat.S_IMODE(self.h.toml.stat().st_mode), 0o600)

    def test_symlinked_file_stays_a_link(self):
        real = self.h.home / 'dotfiles/shell.toml'
        real.parent.mkdir()
        real.write_text('[font]\nsize = 12\n')
        self.h.toml.symlink_to(real)
        self.assertEqual(self.h.run('glass'), 0)
        self.assertTrue(self.h.toml.is_symlink())
        self.assertEqual(tomllib.loads(real.read_text())['bar'], {'background-alpha': 0.55})

    def test_second_run_waits_for_the_lock_then_gives_up(self):
        self.h.toml.write_text('[font]\nsize = 12\n')
        with open(self.h.level.parent / '.lock', 'a') as held, patch.object(g, 'LOCK_WAIT', 0.2):
            fcntl.flock(held, fcntl.LOCK_EX)
            self.assertEqual(self.h.run('solid'), 1)
        self.assertEqual(self.h.toml.read_text(), '[font]\nsize = 12\n')
        self.assertEqual(self.h.run('solid'), 0)

    def test_command_line(self):
        self.assertEqual(self.h.cli().stdout, 'glass\n')
        done = self.h.cli('frosted')
        self.assertEqual((done.returncode, done.stdout), (0, 'frosted\n'))
        self.assertEqual(self.h.cli('next').stdout, 'solid\n')
        self.assertEqual(self.h.cli('next').stdout, 'clear\n')
        self.assertEqual(self.h.cli('prev').stdout, 'solid\n')
        self.assertEqual(self.h.cli().stdout, 'solid\n')
        self.assertEqual(self.h.cli('opaque').returncode, 1)
        self.assertEqual(self.h.cli().stdout, 'solid\n')


if __name__ == '__main__':
    unittest.main()
