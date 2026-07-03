from __future__ import annotations

import argparse
import asyncio

from bench.config import load_prompts, load_profiles, load_targets
from bench.runner import run_benchmark
from bench.schemas import BenchmarkRunConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an LLM wrapper benchmark.")
    parser.add_argument("--targets", default="configs/targets.yaml")
    parser.add_argument("--prompts", default="configs/prompts.yaml")
    parser.add_argument("--profiles", default="configs/test_profiles.yaml")
    parser.add_argument("--profile", default="quick")
    parser.add_argument("--run-name", default="cli-benchmark")
    parser.add_argument("--target-id", action="append", default=None)
    parser.add_argument("--prompt-id", action="append", default=None)
    parser.add_argument("--notes", default=None)
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    targets = [target for target in load_targets(args.targets) if target.enabled]
    prompts = load_prompts(args.prompts)
    profiles = load_profiles(args.profiles)
    if args.target_id:
        targets = [target for target in targets if target.id in set(args.target_id)]
    if args.prompt_id:
        prompts = [prompt for prompt in prompts if prompt.id in set(args.prompt_id)]
    profile = profiles[args.profile]

    run_config = BenchmarkRunConfig(
        name=args.run_name,
        profile_name=args.profile,
        profile=profile,
        targets=targets,
        prompts=prompts,
        notes=args.notes,
        config_paths={
            "targets": args.targets,
            "prompts": args.prompts,
            "profiles": args.profiles,
        },
    )

    def progress(event):
        if event.get("type") == "request_completed":
            print(
                f"{event['completed_requests']}/{event['total_requests']} "
                f"{event['target_id']} {event['prompt_id']} "
                f"status={event['status']} latency={event.get('latest_latency_ms')}"
            )
        elif event.get("type") in {"run_started", "run_completed"}:
            print(event)

    run_id = await run_benchmark(run_config, progress)
    print(f"Completed run: {run_id}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
