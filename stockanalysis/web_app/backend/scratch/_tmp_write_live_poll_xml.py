"""Write a clean, enabled Task Scheduler XML for D24L poller."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
TASK_DIR = BACKEND / "data_cache" / "observation" / "unattended" / "task_scheduler"
PYTHON = Path(os.environ.get("D24L_PYTHON") or sys.executable)
WRAPPER = TASK_DIR / "run_poll.cmd"
XML_PATH = TASK_DIR / "D24L_Observation_Poll.xml"
RUNNER = BACKEND / "scratch" / "run_d2_4l_unattended.py"


def _xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def main() -> int:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    WRAPPER.write_text(
        "\r\n".join(
            [
                "@echo off",
                f'set "PYTHONPATH={BACKEND}"',
                'set "D24L_UNATTENDED=1"',
                f'cd /d "{BACKEND}"',
                f'"{PYTHON}" -u "{RUNNER}" poll',
                "exit /b %ERRORLEVEL%",
                "",
            ]
        ),
        encoding="utf-8",
    )

    wrap = _xml(str(WRAPPER))
    work = _xml(str(BACKEND))
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>D2.4L unattended observation poller (DST-safe via America/New_York). Local Windows only.</Description>
    <URI>\\StockAnalysis\\D24L_Observation_Poll</URI>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT5M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2026-10-27T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <AllowHardTerminate>true</AllowHardTerminate>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT3H</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{wrap}</Command>
      <WorkingDirectory>{work}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""
    # UTF-16 LE with BOM
    XML_PATH.write_bytes(xml.encode("utf-16"))
    print(f"wrote {XML_PATH}")
    print(f"wrapper {WRAPPER}")
    print(f"python {PYTHON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
