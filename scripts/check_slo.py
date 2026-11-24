#!/usr/bin/env python3
"""Сверка slo.json, docs/slo.md, дашборда и правил алертов.

Запуск: uv run --with pyyaml==6.0.4 python scripts/check_slo.py
"""
import json
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise SystemExit(f"FAIL: нужен PyYAML (uv run --with pyyaml==6.0.4 ...): {exc}")

ROOT = Path(__file__).resolve().parent.parent
SLO = ROOT / "deploy/observability/slo.json"
DOC = ROOT / "docs/slo.md"
DASH = ROOT / "deploy/observability/grafana-dashboards/slo.json"
RULES = ROOT / "deploy/observability/grafana-provisioning/alerting/rules.yml"


def fail(msg: str) -> None:
    raise SystemExit(f"FAIL: {msg}")


def main() -> None:
    for path in (SLO, DOC, DASH, RULES):
        if not path.is_file():
            fail(f"нет файла {path.relative_to(ROOT)}")
    slo = json.loads(SLO.read_text(encoding="utf-8"))
    doc = DOC.read_text(encoding="utf-8")
    dash = json.loads(DASH.read_text(encoding="utf-8"))
    data = yaml.safe_load(RULES.read_text(encoding="utf-8"))

    if slo.get("availability", {}).get("target_percent") != 99:
        fail("slo.json: target_percent должен быть 99")
    if slo.get("availability", {}).get("window_days") != 30:
        fail("slo.json: window_days должен быть 30")
    if slo.get("latency_p95_ms") != 800:
        fail("slo.json: latency_p95_ms должен быть 800")
    if slo.get("backup_freshness_hours") != 24 or slo.get("rpo_hours") != 24:
        fail("slo.json: свежесть бэкапа и RPO должны быть 24")
    if slo.get("rto_minutes") != 15:
        fail("slo.json: rto_minutes должен быть 15")
    for token in ("99%", "30", "800", "24", "15"):
        if token not in doc:
            fail(f"docs/slo.md: нет значения {token!r}")
    if dash.get("uid") != slo.get("dashboard_uid"):
        fail("дашборд slo.json: uid не совпадает с dashboard_uid")
    if len(dash.get("panels", [])) != 4:
        fail("дашборд slo.json: ожидается 4 панели")

    uids = {r.get("uid") for g in data.get("groups", []) for r in g.get("rules", [])}
    for uid in slo.get("rule_uids", []):
        if uid not in uids:
            fail(f"rules.yml: нет правила {uid}")
        rule = next(r for g in data["groups"] for r in g["rules"] if r.get("uid") == uid)
        if rule.get("labels", {}).get("enabled") != "false":
            fail(f"{uid}: labels.enabled должен быть \"false\"")
    print("ok: SLO — цели, дашборд и три выключенных правила согласованы")


if __name__ == "__main__":
    main()
