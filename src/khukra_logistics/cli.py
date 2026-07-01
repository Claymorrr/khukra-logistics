"""CLI for Khukra Logistics."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from typing import Any

from khukra_logistics.disruption.service import get_disruption_service
from khukra_logistics.registry import get_model, list_models


def _serialize(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


def _parse_params(pairs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair in pairs:
        key, _, raw = pair.partition("=")
        if not key:
            continue
        if raw.lower() in ("true", "false"):
            out[key] = raw.lower() == "true"
        else:
            try:
                out[key] = int(raw)
            except ValueError:
                try:
                    out[key] = float(raw)
                except ValueError:
                    out[key] = raw
    return out


def _print_json(payload: Any) -> None:
    print(json.dumps(_serialize(payload), indent=2))


def cmd_list(_: argparse.Namespace) -> int:
    for item in list_models():
        print(f"{item['model_id']:28}  {item['subdomain']}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    result = get_model(args.model_id).run(_parse_params(args.param))
    _print_json(result)
    return 0


def cmd_catalog(_: argparse.Namespace) -> int:
    _print_json(get_disruption_service().catalog())
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    _print_json(get_disruption_service().status())
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    _print_json(get_disruption_service().refresh(args.signals, args.years))
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    try:
        _print_json(get_disruption_service().discover(args.signals))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def cmd_forecast(args: argparse.Namespace) -> int:
    try:
        _print_json(get_disruption_service().forecast(args.signals, args.horizon))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def cmd_explore(args: argparse.Namespace) -> int:
    try:
        _print_json(get_disruption_service().explore(args.signals))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    try:
        _print_json(
            get_disruption_service().evaluate(
                args.signals,
                args.horizon,
                persist=not args.no_persist,
            )
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def cmd_evaluation_history(args: argparse.Namespace) -> int:
    _print_json(get_disruption_service().evaluation_history(args.days))
    return 0


def cmd_refresh_news(_: argparse.Namespace) -> int:
    _print_json(get_disruption_service().refresh_news())
    return 0


def cmd_news_status(_: argparse.Namespace) -> int:
    _print_json(get_disruption_service().get_news_status())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="khukra-logistics",
        description="Global disruption forecast and statistical risk discovery",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List simulation models").set_defaults(func=cmd_list)

    run_parser = sub.add_parser("run", help="Run a simulation model")
    run_parser.add_argument("model_id")
    run_parser.add_argument("--param", action="append", default=[])
    run_parser.set_defaults(func=cmd_run)

    sub.add_parser("catalog", help="List disruption signal catalog").set_defaults(func=cmd_catalog)
    sub.add_parser("status", help="Show cached disruption data status").set_defaults(func=cmd_status)

    refresh_parser = sub.add_parser("refresh", help="Pull disruption signals into local cache")
    refresh_parser.add_argument("--signals", nargs="*", default=None)
    refresh_parser.add_argument("--years", type=int, default=5)
    refresh_parser.set_defaults(func=cmd_refresh)

    discover_parser = sub.add_parser("discover", help="Statistical insight discovery on cached panel")
    discover_parser.add_argument("--signals", nargs="*", default=None)
    discover_parser.set_defaults(func=cmd_discover)

    forecast_parser = sub.add_parser("forecast", help="Composite risk forecast")
    forecast_parser.add_argument("--signals", nargs="*", default=None)
    forecast_parser.add_argument("--horizon", type=int, default=30)
    forecast_parser.set_defaults(func=cmd_forecast)

    explore_parser = sub.add_parser("explore", help="Advanced exploratory analysis (PCA, MI, Granger, …)")
    explore_parser.add_argument("--signals", nargs="*", default=None)
    explore_parser.set_defaults(func=cmd_explore)

    evaluate_parser = sub.add_parser(
        "evaluate",
        help="Daily forecast-precision scorecard on hybrid panel",
    )
    evaluate_parser.add_argument("--signals", nargs="*", default=None)
    evaluate_parser.add_argument("--horizon", type=int, default=30)
    evaluate_parser.add_argument("--no-persist", action="store_true")
    evaluate_parser.set_defaults(func=cmd_evaluate)

    history_parser = sub.add_parser("evaluation", help="Show daily evaluation history")
    history_parser.add_argument("--days", type=int, default=30)
    history_parser.set_defaults(func=cmd_evaluation_history)

    sub.add_parser("refresh-news", help="Poll RSS feeds and update news_stress signal").set_defaults(
        func=cmd_refresh_news
    )
    sub.add_parser("news", help="Show cached headline status").set_defaults(func=cmd_news_status)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
