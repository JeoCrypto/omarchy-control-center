"""extras/glass-level: shell.toml is merged, checked and swapped in one step."""
import fcntl
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import signal
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
        self.pending = self.home / '.config/glass/.pending'
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

    def failing_replace(self, *names):
        """os.replace that fails, in order, for the destinations named."""
        real, left = os.replace, list(names)

        def replace(src, dst):
            if left and Path(dst).name == left[0]:
                left.pop(0)
                raise OSError('disk full')
            return real(src, dst)

        return patch.object(g.os, 'replace', side_effect=replace)

    def test_level_file_failure_puts_shell_toml_back(self):
        # shell.toml is swapped, then the level file cannot be written.
        original = '[font]\nsize = 12\n\n[bar]\nposition = "top"\n'
        self.h.toml.write_text(original)
        self.h.toml.chmod(0o600)
        self.h.level.write_text('glass\n')
        with self.failing_replace('level'):
            self.assertEqual(self.h.run('solid'), 1)
        self.assertEqual(self.h.toml.read_text(), original)
        self.assertEqual(stat.S_IMODE(self.h.toml.stat().st_mode), 0o600)
        self.assertEqual(self.h.level.read_text(), 'glass\n')
        self.assertFalse(self.h.pending.exists())
        self.assertEqual(self.h.leftovers(), [])

    def test_level_file_failure_removes_a_shell_toml_it_created(self):
        with self.failing_replace('level'):
            self.assertEqual(self.h.run('solid'), 1)
        self.assertFalse(self.h.toml.exists())
        self.assertFalse(self.h.level.exists())
        self.assertFalse(self.h.pending.exists())

    def test_change_that_could_not_be_undone_is_finished_by_the_next_run(self):
        # The level file cannot be written and shell.toml cannot be put back.
        self.h.toml.write_text('[font]\nsize = 12\n')
        self.h.level.write_text('glass\n')
        with self.failing_replace('level', 'shell.toml'):
            self.assertEqual(self.h.run('solid'), 1)
        self.assertTrue(g.holds(self.h.toml.read_text(), 'solid'))
        self.assertEqual(self.h.level.read_text(), 'glass\n')
        self.assertEqual(self.h.pending.read_text(), 'solid\n')
        # Asking for the level is enough to finish it.
        done = self.h.cli()
        self.assertEqual((done.returncode, done.stdout), (0, 'solid\n'))
        self.assertEqual(self.h.level.read_text(), 'solid\n')
        self.assertFalse(self.h.pending.exists())

    def test_run_killed_between_the_two_files_is_finished_by_the_next_run(self):
        self.h.toml.write_text('[font]\nsize = 12\n')
        self.h.level.write_text('glass\n')

        # A real run, killed after shell.toml was swapped and before the level file.
        code = ('import importlib.machinery, importlib.util, os, signal, sys\n'
                'loader = importlib.machinery.SourceFileLoader("g", sys.argv[1])\n'
                'g = importlib.util.module_from_spec(importlib.util.spec_from_loader("g", loader))\n'
                'loader.exec_module(g)\n'
                'real = g.write_level\n'
                'def write_level(path, level):\n'
                '    if os.path.basename(path) == "level":\n'
                '        os.kill(os.getpid(), signal.SIGKILL)\n'
                '    real(path, level)\n'
                'g.write_level = write_level\n'
                'sys.exit(g.main(["glass-level", "frosted"]))\n')
        done = subprocess.run([sys.executable, '-c', code, str(SCRIPT)], env=self.h.env,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, -signal.SIGKILL)
        self.assertTrue(g.holds(self.h.toml.read_text(), 'frosted'))
        self.assertEqual(self.h.level.read_text(), 'glass\n')
        self.assertEqual(self.h.pending.read_text(), 'frosted\n')
        # The next change finishes the earlier one first, then makes its own.
        self.assertEqual(self.h.cli('next').stdout, 'solid\n')
        self.assertEqual(self.h.level.read_text(), 'solid\n')
        self.assertFalse(self.h.pending.exists())

    def test_note_for_a_change_that_never_happened_is_dropped(self):
        # Killed after the note was written and before shell.toml was swapped.
        self.h.run('glass')
        self.h.pending.write_text('solid\n')
        self.assertEqual(self.h.cli().stdout, 'glass\n')
        self.assertFalse(self.h.pending.exists())
        self.assertTrue(g.holds(self.h.toml.read_text(), 'glass'))
        self.h.pending.write_text('not a level\n')
        self.assertEqual(self.h.run('frosted'), 0)
        self.assertFalse(self.h.pending.exists())

    def test_stop_request_waits_for_both_files(self):
        self.h.toml.write_text('[font]\nsize = 12\n')
        real = g.write_level

        def interrupted(path, level):
            if Path(path) == self.h.level:
                os.kill(os.getpid(), signal.SIGTERM)   # arrives between the two files
            return real(path, level)

        with patch.object(g, 'write_level', side_effect=interrupted):
            with self.assertRaises(SystemExit):
                self.h.run('solid')
        self.assertTrue(g.holds(self.h.toml.read_text(), 'solid'))
        self.assertEqual(self.h.level.read_text(), 'solid\n')
        self.assertFalse(self.h.pending.exists())

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
