"""
query_macro_db.py — 宏观时间序列数据库 CLI 查询工具
用法:
  python scripts/macro_db/query_macro_db.py --series BAMLH0A0HYM2 --start 2000-01-01 --end 2026-06-30
  python scripts/macro_db/query_macro_db.py --series BAMLH0A0HYM2 --out temp/query.csv
  python scripts/macro_db/query_macro_db.py --list
"""
import sys, argparse, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from macro_db_api import load_series, get_metadata, get_latest, get_percentile, list_series


def format_stats(df, meta):
    """格式化统计输出。"""
    d_start = str(df["date"].min())[:10]
    d_end = str(df["date"].max())[:10]
    vals = df["value"].dropna()
    if len(vals) == 0:
        return "No data."

    lines = [
        f"series_id:     {meta.get('series_id', '?')}",
        f"name:          {meta.get('name', '?')}",
        f"start:         {d_start}",
        f"end:           {d_end}",
        f"rows:          {len(df)}",
        f"first_date:    {d_start}",
        f"last_date:     {d_end}",
        f"first_value:   {vals.iloc[0]:.4f}",
        f"last_value:    {vals.iloc[-1]:.4f}",
        f"min:           {vals.min():.4f}",
        f"max:           {vals.max():.4f}",
        f"mean:          {vals.mean():.4f}",
        f"p10:           {vals.quantile(0.10):.4f}",
        f"p25:           {vals.quantile(0.25):.4f}",
        f"p50:           {vals.quantile(0.50):.4f}",
        f"p75:           {vals.quantile(0.75):.4f}",
        f"p90:           {vals.quantile(0.90):.4f}",
        f"p95:           {vals.quantile(0.95):.4f}",
        f"seed_status:   {meta.get('seed_status', '?')}",
        f"history_quality: {meta.get('history_quality', '?')}",
        f"gap_note:      {meta.get('gap_note', 'none')}",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Macro DB Query Tool")
    parser.add_argument("--series", type=str, help="Series ID (e.g. BAMLH0A0HYM2)")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--out", type=str, default=None, help="Output CSV path")
    parser.add_argument("--latest", action="store_true", help="Show latest value only")
    parser.add_argument("--pct", type=float, default=None, help="Get percentile for given value")
    parser.add_argument("--list", action="store_true", help="List all series in DB")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.list:
        series_list = list_series()
        if args.json:
            print(json.dumps(series_list, indent=2, ensure_ascii=False, default=str))
        else:
            for s in series_list:
                print(f"{s['series_id']:20s} {s['name'][:50]:50s} {s['seed_status']:10s} {s['history_quality']:12s} {s['start_date']} → {s['end_date']} ({s['rows']} rows)")
        return

    if not args.series:
        print("Error: --series required (or use --list)")
        sys.exit(1)

    series_id = args.series

    if args.latest:
        row = get_latest(series_id)
        if args.json:
            print(json.dumps(row, indent=2, default=str))
        else:
            print(f"{row.get('date')}: {row.get('value')} (source: {row.get('source_layer')})")
        return

    if args.pct is not None:
        p = get_percentile(series_id, args.pct, args.start, args.end)
        print(f"Percentile of {args.pct}: {p:.4f} ({p*100:.1f}%)")
        return

    df = load_series(series_id, args.start, args.end)
    if df.empty:
        print(f"No data for {series_id}")
        sys.exit(1)

    meta = get_metadata(series_id)

    if args.out:
        df.to_csv(args.out, index=False)
        print(f"Exported to {args.out}")
    else:
        print(format_stats(df, meta))


if __name__ == "__main__":
    main()
