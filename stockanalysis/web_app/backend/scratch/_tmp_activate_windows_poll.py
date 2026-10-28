"""Activate local Windows observation poller only (no DO cron, no broker)."""
from __future__ import annotations

import json
from pathlib import Path

from app.services.observation_schedule import SCHEDULE_PATH, ensure_schedule_config
from app.services.unattended_observation import (
    ACTIVATION_FLAG_PATH,
    TASK_ARTIFACTS_DIR,
    generate_task_scheduler_artifacts,
)


def main() -> int:
    backend = Path(__file__).resolve().parents[1]

    # 1) Local activation flag
    ACTIVATION_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVATION_FLAG_PATH.write_text(
        "approved_local_windows_observation_poller_only\n", encoding="utf-8"
    )

    # 2) Enable Windows observation config only (DO stays false)
    cfg = ensure_schedule_config()
    cfg.setdefault("activation", {})
    cfg["activation"]["windows_task_enabled"] = True
    cfg["activation"]["unattended_enabled"] = True
    cfg["activation"]["digitalocean_cron_enabled"] = False
    cfg["activation"]["note"] = (
        "Local Windows observation poller approved. "
        "DigitalOcean cron remains disabled. Broker execution unchanged."
    )
    cfg["activation"]["activated_scope"] = "StockAnalysis\\D24L_Observation_Poll"
    SCHEDULE_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    # 3) Refresh artifacts then enable trigger+settings in XML for registration
    arts = generate_task_scheduler_artifacts(backend_dir=backend)
    # generate_task_scheduler_artifacts resets activation flags to false — restore
    cfg2 = ensure_schedule_config()
    cfg2.setdefault("activation", {})
    cfg2["activation"]["windows_task_enabled"] = True
    cfg2["activation"]["unattended_enabled"] = True
    cfg2["activation"]["digitalocean_cron_enabled"] = False
    cfg2["activation"]["note"] = cfg["activation"]["note"]
    cfg2["activation"]["activated_scope"] = "StockAnalysis\\D24L_Observation_Poll"
    SCHEDULE_PATH.write_text(json.dumps(cfg2, indent=2), encoding="utf-8")

    xml_path = Path(arts["poll_xml"])
    # Task Scheduler XML is UTF-16; flip Enabled flags for live registration
    text = xml_path.read_text(encoding="utf-16")
    # Enable task settings and trigger (were false for inactive artifacts)
    text = text.replace("<Enabled>false</Enabled>", "<Enabled>true</Enabled>")
    xml_path.write_bytes(("\ufeff" + text).encode("utf-16"))

    print(
        json.dumps(
            {
                "flag_created": ACTIVATION_FLAG_PATH.exists(),
                "flag_path": str(ACTIVATION_FLAG_PATH),
                "schedule_activation": cfg2.get("activation"),
                "poll_xml": str(xml_path),
                "register_script": arts.get("register_script"),
                "wrapper_cmd": str(TASK_ARTIFACTS_DIR / "run_poll.cmd"),
                "digitalocean_cron_enabled": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
