# BAMLH0A0HYM2 External Seed Audit

**Audit timestamp**: 2026-06-21T11:19:36Z

## Summary

- **seed_status**: `partial`
- **history_quality**: `incomplete`
- **total candidates**: 4
- **accepted**: 0
- **partial**: 2

## FRED Live

- {'path': 'D:\\liquidity-dashboard\\v3.5\\data\\macro_db\\raw\\BAMLH0A0HYM2\\fred_live\\BAMLH0A0HYM2_fred_live.csv', 'rows': 795, 'columns': ['observation_date', 'BAMLH0A0HYM2']}

## Download Attempts

- https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2: OK
- GitHub csaladenes/eco-archive: OK
- FRED graph OUJ: OK
- FRED graph qV1C: OK
- FRED graph 1lax: OK
- ?: OK

## Per-Candidate Validation

### Candidate 1: fred_graph_1lax.csv
- **status**: `rejected_bad_values`
- **score**: 10
- **date range**: None → None
- **rows**: 0
- **ERROR**: Exception during normalization: 'utf-8' codec can't decode byte 0xd5 in position 12: invalid continuation byte
- **ERROR**: Traceback (most recent call last):
  File "D:\liquidity-dashboard\v3.5\scripts\macro_db\validate_hy_oas_candidate.py", line 139, in normalize_candidate
    df = pd.read_csv(filepath)
         ^^^^^^^^^^^^^^^^^^^^^
  File "D:\liquidity-dashboard\.venv\Lib\site-packages\pandas\io\parsers\readers.py", line 873, in read_csv
    return _read(filepath_or_buffer, kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\liquidity-dashboard\.venv\Lib\site-packages\pandas\io\parsers\readers.py", line 300, in _read
    parser = TextFileReader(filepath_or_buffer, **kwds)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\liquidity-dashboard\.venv\Lib\site-packages\pandas\io\parsers\readers.py", line 1645, in __init__
    self._engine = self._make_engine(f, self.engine)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\liquidity-dashboard\.venv\Lib\site-packages\pandas\io\parsers\readers.py", line 1922, in _make_engine
    return mapping[engine](f, **self.options)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\liquidity-dashboard\.venv\Lib\site-packages\pandas\io\parsers\c_parser_wrapper.py", line 95, in __init__
    self._reader = parsers.TextReader(src, **kwds)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "pandas/_libs/parsers.pyx", line 568, in pandas._libs.parsers.TextReader.__cinit__
  File "pandas/_libs/parsers.pyx", line 657, in pandas._libs.parsers.TextReader._get_header
  File "pandas/_libs/parsers.pyx", line 868, in pandas._libs.parsers.TextReader._tokenize_rows
  File "pandas/_libs/parsers.pyx", line 885, in pandas._libs.parsers.TextReader._check_tokenize_status
  File "pandas/_libs/parsers.pyx", line 2076, in pandas._libs.parsers.raise_parser_error
  File "<frozen codecs>", line 322, in decode
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xd5 in position 12: invalid continuation byte


### Candidate 2: fred_graph_OUJ.csv
- **status**: `accepted_partial_seed`
- **score**: 80
- **date range**: 2023-06-19 → 2026-06-17
- **rows**: 787
- **overlap**: passed (count=787, match_ratio=1.0, median_diff=0.0)
- WARNING: Coverage insufficient for full seed: start=2023-06-19, end=2026-06-17, rows=787

### Candidate 3: fred_graph_qV1C.csv
- **status**: `rejected_bad_values`
- **score**: 10
- **date range**: None → None
- **rows**: 0
- **ERROR**: Exception during normalization: 'utf-8' codec can't decode byte 0xd5 in position 12: invalid continuation byte
- **ERROR**: Traceback (most recent call last):
  File "D:\liquidity-dashboard\v3.5\scripts\macro_db\validate_hy_oas_candidate.py", line 139, in normalize_candidate
    df = pd.read_csv(filepath)
         ^^^^^^^^^^^^^^^^^^^^^
  File "D:\liquidity-dashboard\.venv\Lib\site-packages\pandas\io\parsers\readers.py", line 873, in read_csv
    return _read(filepath_or_buffer, kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\liquidity-dashboard\.venv\Lib\site-packages\pandas\io\parsers\readers.py", line 300, in _read
    parser = TextFileReader(filepath_or_buffer, **kwds)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\liquidity-dashboard\.venv\Lib\site-packages\pandas\io\parsers\readers.py", line 1645, in __init__
    self._engine = self._make_engine(f, self.engine)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\liquidity-dashboard\.venv\Lib\site-packages\pandas\io\parsers\readers.py", line 1922, in _make_engine
    return mapping[engine](f, **self.options)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\liquidity-dashboard\.venv\Lib\site-packages\pandas\io\parsers\c_parser_wrapper.py", line 95, in __init__
    self._reader = parsers.TextReader(src, **kwds)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "pandas/_libs/parsers.pyx", line 568, in pandas._libs.parsers.TextReader.__cinit__
  File "pandas/_libs/parsers.pyx", line 657, in pandas._libs.parsers.TextReader._get_header
  File "pandas/_libs/parsers.pyx", line 868, in pandas._libs.parsers.TextReader._tokenize_rows
  File "pandas/_libs/parsers.pyx", line 885, in pandas._libs.parsers.TextReader._check_tokenize_status
  File "pandas/_libs/parsers.pyx", line 2076, in pandas._libs.parsers.raise_parser_error
  File "<frozen codecs>", line 322, in decode
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xd5 in position 12: invalid continuation byte


### Candidate 4: github_csaladenes_eco_archive_BAMLH0A0HYM2.csv
- **status**: `accepted_partial_seed`
- **score**: 65
- **date range**: 1996-12-31 → 2021-03-19
- **rows**: 6322
- **overlap**: passed_no_overlap (count=0, match_ratio=None, median_diff=None)
- WARNING: Coverage insufficient for full seed: start=1996-12-31, end=2021-03-19, rows=6322
- WARNING: Seed ends 2021-03-19, FRED live starts 2023-06-19 — gap of ~822 days. Accepted based on direct series column name + value range.

## Best Seed

- **file**: D:\liquidity-dashboard\v3.5\data\macro_db\raw\BAMLH0A0HYM2\external_candidates\fred_graph_OUJ.csv
- **dates**: 2023-06-19 → 2026-06-17
- **rows**: 787
- **score**: 80
- **status**: accepted_partial_seed

## License Note

ICE/FRED raw historical data may be copyrighted. For internal research/backtesting only. Do not redistribute.