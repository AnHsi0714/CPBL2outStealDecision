"""第 1 步：從打者機率檔算出長打力／選球力代理指標，供棒次 × 打者類型分析使用。

依計畫書 3.2 節，刻意不用 SLG/OBP（兩者高度重疊），改用：
  ISO_proxy   = P_2B*1 + P_3B*2 + P_HR*3   （每打席期望額外壘打數，純長打力）
  BBpct_proxy = P_BB_HBP                    （每打席保送/觸身率，純選球力）
兩者再各自以聯盟中位數切成高／低兩組。依計畫書 3.2 的樣本門檻，只取 PA >= min-pa 的打者。

另外算出 OBP_proxy = P_HIT + P_BB_HBP（安打率+保送觸身率，真上壘率）當對照組，
用來驗證「為什麼不能直接用上壘率分組」——OBP 把安打也算進去，會跟 ISO 有更高的相關，
分組結果因此混雜了長打效應，方向可能跟純選球力（BBpct_proxy）相反。

再算出 SingleRate_proxy = P_1B（純單打率），對應計畫書 1.4 節「高上壘接觸型」（單打即可得分）
的概念——這個指標刻意排除長打，跟 ISO 是負相關，比 OBP 更乾淨，是驗證 1.4 節假設最直接的指標。

最後算出 TTO_proxy = P_K + P_HR + P_BB_HBP（三振率+全壘打率+保送觸身率，Three True Outcomes），
對應計畫書第 4-6 週工作項目：三振率不進 P_OUT 之外另計，三者皆是「打席結果不太受野手守備影響」
的事件。TTO 型打者本質上是 ISO 型與 BBpct 型的疊加（高長打、高選球通常也伴隨高三振），
因此 TTO 分組預期方向會與 PowerGroup／PatienceGroup 一致（TTO 高→門檻高），
用來檢驗「複合純三真傾向」是否比單一指標訊號更強或只是重複。
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import median
from typing import Any


def as_float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def load_profiles(path: Path, min_pa: float) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    kept = [row for row in rows if as_float(row, "PA") >= min_pa]
    return kept


def annotate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    iso_values = []
    bb_values = []
    obp_values = []
    single_values = []
    tto_values = []
    for row in rows:
        iso = as_float(row, "P_2B") * 1 + as_float(row, "P_3B") * 2 + as_float(row, "P_HR") * 3
        bb = as_float(row, "P_BB_HBP")
        obp = as_float(row, "P_HIT") + bb
        single = as_float(row, "P_1B")
        tto = as_float(row, "P_K") + as_float(row, "P_HR") + bb
        row["ISO_proxy"] = iso
        row["BBpct_proxy"] = bb
        row["OBP_proxy"] = obp
        row["SingleRate_proxy"] = single
        row["TTO_proxy"] = tto
        iso_values.append(iso)
        bb_values.append(bb)
        obp_values.append(obp)
        single_values.append(single)
        tto_values.append(tto)

    iso_median = median(iso_values)
    bb_median = median(bb_values)
    obp_median = median(obp_values)
    single_median = median(single_values)
    tto_median = median(tto_values)
    for row in rows:
        row["PowerGroup"] = "high_ISO" if row["ISO_proxy"] >= iso_median else "low_ISO"
        row["PatienceGroup"] = "high_BB" if row["BBpct_proxy"] >= bb_median else "low_BB"
        row["OBPGroup"] = "high_OBP" if row["OBP_proxy"] >= obp_median else "low_OBP"
        row["ContactGroup"] = "high_1B" if row["SingleRate_proxy"] >= single_median else "low_1B"
        row["TTOGroup"] = "high_TTO" if row["TTO_proxy"] >= tto_median else "low_TTO"
    return rows, iso_median, bb_median, obp_median, single_median, tto_median


def correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denom_left = sum((x - left_mean) ** 2 for x in left) ** 0.5
    denom_right = sum((y - right_mean) ** 2 for y in right) ** 0.5
    denominator = denom_left * denom_right
    return numerator / denominator if denominator else None


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        raise RuntimeError(f"{path} 沒有資料")
    fieldnames = [
        "HitterAcnt", "HitterName", "PA",
        "ISO_proxy", "BBpct_proxy", "OBP_proxy", "SingleRate_proxy", "TTO_proxy",
        "PowerGroup", "PatienceGroup", "OBPGroup", "ContactGroup", "TTOGroup",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--kind-code", default="A")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=360)
    parser.add_argument("--profiles-csv", type=Path)
    parser.add_argument("--min-pa", type=float, default=100.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tag = f"{args.year}_{args.kind_code}_{args.start}-{args.end}"
    profiles_csv = args.profiles_csv or Path("outputs") / f"cpbl_batter_profiles_{tag}.csv"
    output = args.output or Path("outputs") / f"cpbl_batter_types_{tag}.csv"

    rows = load_profiles(profiles_csv, args.min_pa)
    if not rows:
        raise SystemExit(f"沒有打席數 >= {args.min_pa} 的打者，無法分組")

    rows, iso_median, bb_median, obp_median, single_median, tto_median = annotate(rows)
    write_csv(rows, output)

    corr_bb = correlation([r["ISO_proxy"] for r in rows], [r["BBpct_proxy"] for r in rows])
    corr_obp = correlation([r["ISO_proxy"] for r in rows], [r["OBP_proxy"] for r in rows])
    corr_single = correlation([r["ISO_proxy"] for r in rows], [r["SingleRate_proxy"] for r in rows])
    corr_tto = correlation([r["ISO_proxy"] for r in rows], [r["TTO_proxy"] for r in rows])

    print(f"符合 PA >= {args.min_pa} 的打者：{len(rows)} 位")
    print(f"ISO_proxy 中位數：{iso_median:.4f}")
    print(f"BBpct_proxy 中位數：{bb_median:.4f}")
    print(f"OBP_proxy 中位數：{obp_median:.4f}")
    print(f"SingleRate_proxy 中位數：{single_median:.4f}")
    print(f"TTO_proxy 中位數：{tto_median:.4f}")
    print(f"ISO_proxy 與 BBpct_proxy 相關係數：{corr_bb:.4f}" if corr_bb is not None else "ISO 與 BB% 相關係數：無法計算")
    print(f"ISO_proxy 與 OBP_proxy 相關係數：{corr_obp:.4f}" if corr_obp is not None else "ISO 與 OBP 相關係數：無法計算")
    print(f"ISO_proxy 與 SingleRate_proxy 相關係數：{corr_single:.4f}" if corr_single is not None else "ISO 與 SingleRate 相關係數：無法計算")
    print(f"ISO_proxy 與 TTO_proxy 相關係數：{corr_tto:.4f}" if corr_tto is not None else "ISO 與 TTO 相關係數：無法計算")
    print("分組人數：")
    print(f"  high_ISO / low_ISO   = {sum(r['PowerGroup']=='high_ISO' for r in rows)} / {sum(r['PowerGroup']=='low_ISO' for r in rows)}")
    print(f"  high_BB  / low_BB    = {sum(r['PatienceGroup']=='high_BB' for r in rows)} / {sum(r['PatienceGroup']=='low_BB' for r in rows)}")
    print(f"  high_OBP / low_OBP   = {sum(r['OBPGroup']=='high_OBP' for r in rows)} / {sum(r['OBPGroup']=='low_OBP' for r in rows)}")
    print(f"  high_1B  / low_1B    = {sum(r['ContactGroup']=='high_1B' for r in rows)} / {sum(r['ContactGroup']=='low_1B' for r in rows)}")
    print(f"  high_TTO / low_TTO   = {sum(r['TTOGroup']=='high_TTO' for r in rows)} / {sum(r['TTOGroup']=='low_TTO' for r in rows)}")
    print(f"輸出：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
