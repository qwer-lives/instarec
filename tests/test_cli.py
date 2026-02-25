import subprocess


def test_cli_help_command():
    result = subprocess.run(["instarec", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Download Instagram live streams" in result.stdout


def test_cli_version_command():
    result = subprocess.run(["instarec", "--version"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "instarec" in result.stdout
    assert "unknown" not in result.stdout
