#!/usr/bin/env python3
"""Read-only проверка compose-профилей метрик и датасорса Grafana (issue #14).

Проверяет согласованность Prometheus/node_exporter/blackbox_exporter и Grafana
без запуска сервисов. Опциональный argv[1] задаёт корень репозитория — для
негативных тестов. Реальный адрес сайта в конфигурации запрещён.
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
OBS = ROOT / "deploy" / "observability"


def fail(message):
    raise SystemExit(f"FAIL: {message}")


def load(relative):
    path = OBS / relative
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        fail(f"{relative}: не удалось прочитать YAML: {exc}")


def main():
    compose = load("docker-compose.yml")
    services = compose.get("services") if isinstance(compose, dict) else None
    if not isinstance(services, dict):
        fail("docker-compose.yml: нет services")

    for name in ("prometheus", "node-exporter", "blackbox-exporter"):
        service = services.get(name)
        if not isinstance(service, dict):
            fail(f"docker-compose.yml: нет сервиса {name}")
        profiles = service.get("profiles")
        if not isinstance(profiles, list) or "logs" not in profiles:
            fail(f"{name}: сервис должен быть под профилем logs")

    for name in ("loki", "alloy", "grafana"):
        service = services.get(name)
        if not isinstance(service, dict) or service.get("profiles"):
            fail(f"{name}: базовый контур не должен зависеть от профилей")

    blackbox = load("blackbox.yml")
    modules = blackbox.get("modules") if isinstance(blackbox, dict) else None
    probe = modules.get("http_2xx") if isinstance(modules, dict) else None
    if not isinstance(probe, dict) or probe.get("prober") != "http":
        fail("blackbox.yml: нужен модуль http_2xx с prober: http")
    if str(probe.get("timeout")) != "15s":
        fail("blackbox.yml: timeout должен быть 15s")
    http = probe.get("http")
    if not isinstance(http, dict) or http.get("valid_status_codes") != [200]:
        fail("blackbox.yml: ожидается valid_status_codes: [200]")

    prometheus = load("prometheus.yml")
    jobs = prometheus.get("scrape_configs") if isinstance(prometheus, dict) else None
    if not isinstance(jobs, list):
        fail("prometheus.yml: нет scrape_configs")
    names = {job.get("job_name") for job in jobs if isinstance(job, dict)}
    for name in ("prometheus", "alloy", "node", "blackbox"):
        if name not in names:
            fail(f"prometheus.yml: нет job {name}")
    active = (OBS / "prometheus.yml").read_text(encoding="utf-8")
    if "sreda-external" in active:
        fail("prometheus.yml: внешняя проба должна оставаться в шаблоне до Q-1")

    template = (OBS / "prometheus-external.yml.template").read_text(encoding="utf-8")
    if "${SREDA_SITE_URL}" not in template:
        fail("шаблон внешней пробы должен использовать ${SREDA_SITE_URL}")
    if "sreda.sielom.ru" in template:
        fail("шаблон не должен содержать реальный адрес")
    for needle in ("job_name: sreda-external", "metrics_path: /probe", "blackbox-exporter:9115"):
        if needle not in template:
            fail(f"шаблон внешней пробы: нет '{needle}'")
    try:
        rendered = yaml.safe_load(template.replace("${SREDA_SITE_URL}", "https://sreda.invalid"))
    except yaml.YAMLError as exc:
        fail(f"шаблон внешней пробы: некорректный YAML: {exc}")
    rendered_jobs = rendered.get("scrape_configs") if isinstance(rendered, dict) else None
    if not isinstance(rendered_jobs, list) or not any(
        isinstance(job, dict) and job.get("job_name") == "sreda-external" for job in rendered_jobs
    ):
        fail("шаблон внешней пробы: после подстановки нет job sreda-external")

    datasources = load("grafana-provisioning/datasources/datasources.yml")
    sources = datasources.get("datasources") if isinstance(datasources, dict) else None
    if not isinstance(sources, list):
        fail("datasources.yml: нет datasources")
    prom = [item for item in sources if isinstance(item, dict) and item.get("uid") == "prometheus"]
    if len(prom) != 1 or prom[0].get("url") != "http://prometheus:9090":
        fail("Grafana: датасорс prometheus должен указывать на http://prometheus:9090")

    adr = (ROOT / "docs/adr/0005-observability-glitchtip.md").read_text(encoding="utf-8")
    if "--profile logs" not in adr or "ADR 0006" not in adr:
        fail("ADR 0005 должен описывать профиль logs и ресурсный gate ADR 0006")
    status = (ROOT / "docs/DEVOPS-STATUS.md").read_text(encoding="utf-8")
    if "`--profile logs`" not in status:
        fail("DEVOPS-STATUS должен упоминать --profile logs")

    print("ok: profiles/logs — Prometheus, node_exporter, blackbox_exporter; Grafana datasource согласован; внешняя проба в шаблоне")


if __name__ == "__main__":
    main()
