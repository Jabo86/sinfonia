"""
Sinfonia — CLI

Comandi disponibili:
    sinfonia status      — quote residue di tutti i provider
    sinfonia usage       — statistiche d'uso (richieste, token, costi)
    sinfonia providers   — elenco provider configurati
    sinfonia models      — elenco modelli disponibili
    sinfonia update      — forza un ciclo di aggiornamento modelli
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config_loader import load_config
from quota_manager import QuotaManager
from router import Router
from transparency import UsageTracker, format_number, format_usd, render_status_table


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


async def cmd_status(args):
    """Mostra quote residue di tutti i provider."""
    cfg = load_config(
        providers_path=PROJECT_ROOT / "config" / "providers.yaml",
        budget_path=PROJECT_ROOT / "config" / "budget.yaml",
        env_path=PROJECT_ROOT / ".env",
    )
    qm = QuotaManager(PROJECT_ROOT / "data" / "sinfonia.db")

    rows = []
    for pid, provider in cfg.free_providers.items():
        api_key = cfg.get_api_key(pid)
        limits = provider.free_tier.limits if provider.free_tier else {}
        status = await qm.get_status(
            pid,
            rpm_limit=limits.get("rpm"),
            rpd_limit=limits.get("rpd"),
            tpd_limit=limits.get("tokens_per_day"),
        )
        rows.append({
            "name": provider.name + ("" if api_key else " (no key)"),
            "rpm_used": status.requests_this_minute,
            "rpm_limit": status.rpm_limit,
            "rpd_used": status.requests_today,
            "rpd_limit": status.rpd_limit,
            "available": status.is_available,
            "in_cooldown": status.is_in_cooldown,
            "cooldown_remaining": status.cooldown_remaining,
        })

    print("\n🎼 Sinfonia — Stato Provider\n")
    print(render_status_table(rows))
    print()


async def cmd_usage(args):
    """Mostra statistiche d'uso."""
    cfg = load_config(
        providers_path=PROJECT_ROOT / "config" / "providers.yaml",
        budget_path=PROJECT_ROOT / "config" / "budget.yaml",
        env_path=PROJECT_ROOT / ".env",
    )
    tracker = UsageTracker(PROJECT_ROOT / "data" / "sinfonia.db")

    print("\n📊 Sinfonia — Statistiche Uso (ultimi 30 giorni)\n")
    print(f"{'Provider':<25} {'Oggi':>8} {'Token oggi':>12} {'Token mese':>12}")
    print("─" * 62)

    for pid, provider in cfg.free_providers.items():
        s = await tracker.get_usage(pid)
        print(f"{provider.name:<25} {s.requests_today:>8} {format_number(s.tokens_today):>12} {format_number(s.tokens_this_month):>12}")

    print()


async def cmd_providers(args):
    """Elenco provider configurati."""
    cfg = load_config(
        providers_path=PROJECT_ROOT / "config" / "providers.yaml",
        budget_path=PROJECT_ROOT / "config" / "budget.yaml",
        env_path=PROJECT_ROOT / ".env",
    )
    print("\n🎼 Sinfonia — Provider Configurati\n")
    print(f"{'ID':<22} {'Nome':<25} {'Chiave':<10} {'Tipo':<8}")
    print("─" * 70)

    for pid, p in cfg.free_providers.items():
        has_key = "✅" if cfg.get_api_key(pid) else "❌"
        print(f"{pid:<22} {p.name:<25} {has_key:<10} {'free':<8}")

    for pid, p in cfg.paid_providers.items():
        has_key = "✅" if cfg.get_api_key(pid) else "❌"
        print(f"{pid:<22} {p.name:<25} {has_key:<10} {'paid':<8}")

    print()


async def cmd_models(args):
    """Elenco modelli disponibili."""
    cfg = load_config(
        providers_path=PROJECT_ROOT / "config" / "providers.yaml",
        budget_path=PROJECT_ROOT / "config" / "budget.yaml",
        env_path=PROJECT_ROOT / ".env",
    )
    print("\n🤖 Sinfonia — Modelli Disponibili\n")
    for pid, p in cfg.free_providers.items():
        if not cfg.get_api_key(pid):
            continue
        print(f"  {p.name}:")
        for m in p.models:
            print(f"    - {m}")
        print()


async def cmd_update(args):
    """Forza un ciclo di aggiornamento modelli."""
    from model_updater import run_update_cycle
    await run_update_cycle(
        PROJECT_ROOT / "config" / "providers.yaml",
        load_config,
    )


def main():
    parser = argparse.ArgumentParser(prog="sinfonia", description="Sinfonia CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Quote residue").set_defaults(func=cmd_status)
    sub.add_parser("usage", help="Statistiche uso").set_defaults(func=cmd_usage)
    sub.add_parser("providers", help="Provider configurati").set_defaults(func=cmd_providers)
    sub.add_parser("models", help="Modelli disponibili").set_defaults(func=cmd_models)
    sub.add_parser("update", help="Aggiorna modelli").set_defaults(func=cmd_update)

    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
