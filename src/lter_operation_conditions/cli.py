import argparse
from pathlib import Path

from lter_operation_conditions import api, gfswave
from lter_operation_conditions.deployments import conditions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wind and sea state at each NES-LTER cruise deployment."
    )
    parser.add_argument("cruises", nargs="*", help="cruise name(s), e.g. en715")
    parser.add_argument(
        "--all", action="store_true", help="process every NES-LTER cruise"
    )
    parser.add_argument(
        "--no-gfs", action="store_true", help="skip the GFS-Wave model lookup"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("conditions.parquet"),
        help="output parquet path",
    )
    parser.add_argument(
        "--csv", action="store_true", help="also write a CSV next to the parquet"
    )
    args = parser.parse_args()

    if args.all:
        names = api.cruises()["cruise"].to_list()
    elif args.cruises:
        names = [c.lower() for c in args.cruises]
    else:
        parser.error("give cruise name(s) or --all")

    df = conditions(names)
    if not args.no_gfs:
        wave = gfswave.compile_wave(df).unique(gfswave.KEYS)
        df = df.join(wave, on=gfswave.KEYS, how="left")
    df.write_parquet(args.out)
    if args.csv:
        df.write_csv(args.out.with_suffix(".csv"))
    print(
        f"wrote {df.height} deployments from {df['cruise'].n_unique()} cruise(s) to {args.out}"
    )
