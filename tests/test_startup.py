from subprocess import list2cmdline

from astropanel.services import startup


def test_frozen_startup_launches_executable_without_python_module(monkeypatch):
    monkeypatch.setattr(startup.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(startup.sys, 'executable', r'C:\Program Files\AstroPanel\AstroPanel.exe')
    assert startup.startup_command() == list2cmdline([startup.sys.executable])


def test_checkout_startup_uses_absolute_windowed_launcher(monkeypatch, tmp_path):
    monkeypatch.setattr(startup.sys, 'frozen', False, raising=False)
    monkeypatch.setattr(startup, '__file__', str(tmp_path / 'src/astropanel/services/startup.py'))
    interpreter = tmp_path / 'Python runtime'
    interpreter.mkdir()
    (interpreter / 'pythonw.exe').touch()
    monkeypatch.setattr(startup.sys, 'executable', str(interpreter / 'python.exe'))
    launcher = tmp_path / 'run_astropanel.py'
    launcher.touch()
    assert startup.startup_command() == list2cmdline([str(interpreter / 'pythonw.exe'), str(launcher)])


def test_installed_package_startup_falls_back_to_module(monkeypatch, tmp_path):
    monkeypatch.setattr(startup.sys, 'frozen', False, raising=False)
    monkeypatch.setattr(startup, '__file__', str(tmp_path / 'lib/astropanel/services/startup.py'))
    monkeypatch.setattr(startup.sys, 'executable', str(tmp_path / 'python.exe'))
    assert startup.startup_command() == list2cmdline([startup.sys.executable, '-m', 'astropanel.app'])
