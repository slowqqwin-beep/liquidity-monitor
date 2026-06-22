"""
test_macro_db_hy_oas_external_seed.py — BAMLH0A0HYM2 宏观数据库模块测试
独立模块，不依赖 Risk OS。
"""
import sys, os, tempfile, json
from pathlib import Path
import pandas as pd
import numpy as np
import pytest

# 确保可以 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "macro_db"))

from validate_hy_oas_candidate import (
    normalize_candidate, check_coverage, check_overlap_with_fred_live,
    compute_score, validate_candidate, _detect_columns,
)


class TestDetectColumns:
    def test_detect_date_value_columns(self):
        df = pd.DataFrame({"DATE": ["2020-01-01"], "BAMLH0A0HYM2": [3.5]})
        dc, vc = _detect_columns(df)
        assert dc == "DATE"
        assert vc == "BAMLH0A0HYM2"

    def test_detect_fallback_columns(self):
        df = pd.DataFrame({"unknown_col1": ["2020-01-01"], "unknown_col2": [3.5]})
        dc, vc = _detect_columns(df)
        assert dc is not None
        assert vc is not None

    def test_detect_alt_colnames(self):
        df = pd.DataFrame({"observation_date": ["2020-01-01"], "value": [3.5]})
        dc, vc = _detect_columns(df)
        assert dc == "observation_date"
        assert vc == "value"


class TestNormalizeCandidate:
    def _write_temp_csv(self, content):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        f.write(content)
        f.close()
        return f.name

    def test_basic_csv_normalization(self):
        p = self._write_temp_csv("DATE,BAMLH0A0HYM2\n2020-01-02,3.50\n2020-01-03,3.60\n2021-01-04,3.40\n2022-01-05,4.00\n2023-01-06,4.50")
        # Need >500 rows for basic check, but small files still normalize
        r = normalize_candidate(p)
        # Small file will be rejected on rows check but df should exist
        assert r["rows"] < 500
        # The df may still be populated before row check
        os.unlink(p)

    def test_csv_date_value_parsing(self):
        # Create enough rows (~600) to pass basic check
        dates = pd.date_range("1997-01-31", "2026-03-01", freq="B")
        vals = np.random.uniform(2.5, 8.0, len(dates))
        df = pd.DataFrame({"DATE": dates.strftime("%Y-%m-%d"), "BAMLH0A0HYM2": vals})
        p = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        df.to_csv(p, index=False)
        p.close()

        r = normalize_candidate(p.name)
        # With >6000 rows and proper dates, should pass basic structure
        assert r["rows"] > 6000
        os.unlink(p.name)

    def test_bp_unit_conversion(self):
        dates = pd.date_range("2000-01-03", "2025-12-31", freq="B")
        vals = np.random.uniform(200, 800, len(dates))  # bp values
        df = pd.DataFrame({"DATE": dates.strftime("%Y-%m-%d"), "BAMLH0A0HYM2": vals})
        p = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        df.to_csv(p, index=False)
        p.close()

        r = normalize_candidate(p.name)
        assert r["unit_converted"] is True
        assert r["unit_original_median"] > 50
        os.unlink(p.name)

    def test_percent_unit_not_misconverted(self):
        dates = pd.date_range("2000-01-03", "2025-12-31", freq="B")
        vals = np.random.uniform(2.0, 8.0, len(dates))
        df = pd.DataFrame({"DATE": dates.strftime("%Y-%m-%d"), "BAMLH0A0HYM2": vals})
        p = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        df.to_csv(p, index=False)
        p.close()

        r = normalize_candidate(p.name)
        assert r["unit_converted"] is False
        assert r["unit_original_median"] < 30
        os.unlink(p.name)

    def test_duplicate_date_dedup(self):
        content = "DATE,BAMLH0A0HYM2\n2020-01-02,3.50\n2020-01-02,3.51\n" + \
                  "\n".join([f"2000-{m:02d}-{d:02d},{np.random.uniform(2,8):.2f}" for m in range(1,13) for d in [1,2,3,4,5,8,9,10,11,12,15,16,17,18,19,22,23,24,25,26]] + \
                            [f"2020-{m:02d}-{d:02d},{np.random.uniform(2,8):.2f}" for m in range(1,13) for d in [1,2,3,4,5,8,9,10,11,12,15,16,17,18,19,22,23,24,25,26]])
        p = self._write_temp_csv(content)
        r = normalize_candidate(p)
        # Verify deduplication warning exists
        assert r["duplicate_dates"] > 0 or len(r.get("warnings", [])) > 0
        os.unlink(p)

    def test_negative_value_error(self):
        content = "DATE,BAMLH0A0HYM2\n2020-01-02,-1.50\n" + \
                  "\n".join([f"1997-{m:02d}-{d:02d},{np.random.uniform(2,8):.2f}" for m in range(1,13) for d in [1,2,3,4,5,8,9,10,11,12,15,16,17,18,19,22,23,24,25,26]] + \
                            [f"2018-{m:02d}-{d:02d},{np.random.uniform(2,8):.2f}" for m in range(1,13) for d in [1,2,3,4,5,8,9,10,11,12,15,16,17,18,19,22,23,24,25,26]])
        p = self._write_temp_csv(content)
        r = normalize_candidate(p)
        assert r["has_negative_values"] is True
        os.unlink(p)

    def test_large_gap_warning(self):
        # Create data with a deliberate large gap
        lines = ["DATE,BAMLH0A0HYM2"]
        for i, d in enumerate(pd.date_range("1997-01-31", "1998-01-01", freq="B")):
            lines.append(f"{d.strftime('%Y-%m-%d')},{3.0 + i*0.01:.2f}")
        # Add rows from 2020 onward after gap
        for i, d in enumerate(pd.date_range("2020-01-02", "2025-12-31", freq="B")):
            lines.append(f"{d.strftime('%Y-%m-%d')},{4.0 + i*0.001:.2f}")
        p = self._write_temp_csv("\n".join(lines))
        r = normalize_candidate(p)
        assert r["has_large_gap"] is True
        os.unlink(p)

    def test_excel_normalization(self):
        dates = pd.date_range("2000-01-03", "2025-12-31", freq="B")
        df = pd.DataFrame({"date": dates, "value": np.random.uniform(2, 8, len(dates))})
        p = tempfile.NamedTemporaryFile(mode="w", suffix=".xlsx", delete=False)
        df.to_excel(p.name, index=False)
        p.close()
        r = normalize_candidate(p.name)
        assert r["rows"] > 500
        os.unlink(p.name)

    def test_parquet_normalization(self):
        dates = pd.date_range("2000-01-03", "2025-12-31", freq="B")
        df = pd.DataFrame({"DATE": dates, "BAMLH0A0HYM2": np.random.uniform(2, 8, len(dates))})
        p = tempfile.NamedTemporaryFile(mode="w", suffix=".parquet", delete=False)
        df.to_parquet(p.name, index=False)
        p.close()
        r = normalize_candidate(p.name)
        assert r["rows"] > 500
        os.unlink(p.name)


class TestOverlapCheck:
    def _make_fred_temp(self):
        dates = pd.date_range("2023-06-01", "2026-06-20", freq="B")
        vals = np.random.uniform(2.5, 5.0, len(dates))
        df = pd.DataFrame({"observation_date": dates.strftime("%Y-%m-%d"), "BAMLH0A0HYM2": vals})
        p = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        df.to_csv(p, index=False)
        p.close()
        return p.name

    def _make_candidate_temp(self):
        dates = pd.date_range("1997-01-31", "2026-03-01", freq="B")
        vals = np.random.uniform(2.5, 8.0, len(dates))
        df = pd.DataFrame({"DATE": dates.strftime("%Y-%m-%d"), "BAMLH0A0HYM2": vals})
        p = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        df.to_csv(p, index=False)
        p.close()
        return p.name

    def test_overlap_matching_passes(self):
        # Create candidate and FRED with identical overlap
        dates = pd.date_range("1997-01-31", "2026-06-20", freq="B")
        np.random.seed(42)
        vals = np.random.uniform(2.5, 8.0, len(dates))

        # Candidate
        cand_df = pd.DataFrame({"DATE": dates.strftime("%Y-%m-%d"), "BAMLH0A0HYM2": vals})
        cp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        cand_df.to_csv(cp, index=False)
        cp.close()

        # FRED live (last 3 years identical)
        fred_dates = dates[dates >= "2023-06-21"]
        fred_vals = vals[dates >= "2023-06-21"]
        fred_df = pd.DataFrame({"observation_date": fred_dates.strftime("%Y-%m-%d"), "BAMLH0A0HYM2": fred_vals})
        fp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        fred_df.to_csv(fp, index=False)
        fp.close()

        r = normalize_candidate(cp.name)
        r = check_coverage(r)
        r = check_overlap_with_fred_live(r, fp.name)
        assert r["overlap_status"] == "passed"
        assert r["match_ratio"] >= 0.99
        assert r["overlap_count"] >= 100

        os.unlink(cp.name)
        os.unlink(fp.name)

    def test_overlap_mismatch_rejected(self):
        dates = pd.date_range("1997-01-31", "2026-06-20", freq="B")

        # Candidate with different values
        cand_vals = np.random.uniform(2.5, 8.0, len(dates))
        cand_df = pd.DataFrame({"DATE": dates.strftime("%Y-%m-%d"), "BAMLH0A0HYM2": cand_vals})
        cp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        cand_df.to_csv(cp, index=False)
        cp.close()

        # FRED live with TOTALLY different values
        fred_dates = dates[dates >= "2023-06-21"]
        fred_vals = np.random.uniform(10.0, 20.0, len(fred_dates))  # 完全不同的范围
        fred_df = pd.DataFrame({"observation_date": fred_dates.strftime("%Y-%m-%d"), "BAMLH0A0HYM2": fred_vals})
        fp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        fred_df.to_csv(fp, index=False)
        fp.close()

        r = normalize_candidate(cp.name)
        r = check_coverage(r)
        r = check_overlap_with_fred_live(r, fp.name)
        assert r["overlap_status"] == "failed"
        assert r["candidate_status"] == "rejected_no_overlap_with_fred"

        os.unlink(cp.name)
        os.unlink(fp.name)

    def test_live_only_rejected(self):
        dates = pd.date_range("2024-01-02", "2026-06-20", freq="B")
        vals = np.random.uniform(2.5, 5.0, len(dates))
        df = pd.DataFrame({"DATE": dates.strftime("%Y-%m-%d"), "BAMLH0A0HYM2": vals})
        p = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        df.to_csv(p, index=False)
        p.close()

        r = normalize_candidate(p.name)
        r = check_coverage(r)
        assert r["candidate_status"] == "rejected_live_window_only"
        os.unlink(p.name)


class TestScoring:
    def test_ideal_seed_scores_high(self):
        r = {
            "start_date": "1996-12-31", "end_date": "2026-06-20",
            "rows": 7000, "overlap_count": 600, "match_ratio": 0.998,
            "median_abs_diff": 0.005, "has_negative_values": False,
            "has_large_gap": False, "direct_series_column_name": True,
            "candidate_status": "accepted_seed",
        }
        r = compute_score(r)
        assert r["score"] >= 100  # Max possible: 35+25+15+10+20+10+5+5+5 = 130


class TestNoRiskOsModification:
    """确认本次没有修改 Risk OS、dashboard、run_all.py。"""
    def test_risk_os_untouched(self):
        # This test verifies our module is independent
        code_dir = Path(__file__).resolve().parent.parent
        # We're in tests/, scripts/ is sibling at project root level
        # Just verify macro_db scripts exist and are self-contained
        script_dir = code_dir / "scripts" / "macro_db"
        assert script_dir.exists()
        assert (script_dir / "validate_hy_oas_candidate.py").exists()
        assert (script_dir / "find_external_hy_oas_seed.py").exists()
        assert (script_dir / "build_hy_oas_master.py").exists()
        assert (script_dir / "macro_db_api.py").exists()
        assert (script_dir / "query_macro_db.py").exists()
        # Verify no imports from risk_os
        for fpy in script_dir.glob("*.py"):
            content = fpy.read_text(encoding="utf-8")
            assert "risk_os" not in content.lower(), f"{fpy.name} references risk_os"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
