"""合併分店銷售：每個分店一張明細，合併成一份 Excel（ADR 0020 的 Python 節點範例）。

入參 branches：``{分店: [[品項, 金額], …]}``。產出檔案 ``outputs/合併銷售.xlsx``；
事實 rows（列數）、total（總額）、sheet（工作表名稱）給出參與 verify 用。
"""

from report import merge, write_excel

from rpa_script import Run, StepError, automation


@automation
def main(run: Run) -> None:
    branches = run.inputs["branches"]
    if not branches:
        raise StepError("沒有任何分店的資料")
    with run.step("merge", "合併各分店的明細"):
        merged = merge(branches)
        run.preview("合併結果", merged)
    with run.step("excel", "寫成 Excel"):
        target = run.output_dir / "合併銷售.xlsx"
        sheet = write_excel(merged, target)
        run.log(f"{target.name}：{len(merged)} 列")
    run.facts.update(rows=len(merged), total=float(merged["金額"].sum()), sheet=sheet)
