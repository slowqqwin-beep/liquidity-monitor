import json
d = json.load(open('liquidity-dashboard/data/series.json', 'r', encoding='utf-8'))
for name in ['EFFR', 'SOFR', 'IORB']:
    v = d.get(name, [])
    if v:
        tail = [(r['date'], r['value']) for r in v[-10:]]
        print(f'{name} rows={len(v)}, last 10:')
        for date, val in tail:
            print(f'  {date}  {val}')
        print()
