"""分店彙總：讀上游下載的銷售明細 CSV，依分店加總（ADR 0020 的「瀏覽器＋Python」範例）。

入參 report 是檔案入參：``run.input_files["report"]`` 是這台電腦上的檔案。產出的彙總檔寫在
``run.output_dir``，事實 summary 指向它，出參 ``type: file`` 把它交給下游節點。
"""

import csv
from collections import defaultdict

from rpa_script import Run, StepError, automation


@automation
def main(run: Run) -> None:
    source = run.input_files["report"][0]
    totals: dict[str, int] = defaultdict(int)
    with run.step("read", "讀取銷售明細"):
        with source.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            raise StepError(f"{source.name} 沒有任何資料")
        run.preview("銷售明細", rows)
    with run.step("sum", "依分店加總"):
        for row in rows:
            totals[row["分店"]] += int(row["金額"])
        run.preview("分店彙總", [{"分店": name, "金額": amount} for name, amount in totals.items()])
    with run.step("write", "寫出彙總檔"):
        target = run.output_dir / "分店彙總.csv"
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["分店", "金額"])
            writer.writerows(sorted(totals.items()))
    run.facts.update(total=sum(totals.values()), byBranch=dict(totals), summary=str(target))
