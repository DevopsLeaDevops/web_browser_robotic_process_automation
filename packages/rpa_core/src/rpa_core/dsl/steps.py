"""步驟：M1 的九個動作，加上 M4 為錄製稿加入的 check（勾選）。

每個步驟以 ``action`` 區分種類，共同欄位是 id、name、timeout。
步驟內欄位之間的規則（例如 waitFor 三選一）在各模型的 model_validator 檢查；
跨步驟的規則（id 重複、引用未宣告的參數）在 rpa_core.dsl.checks。

retry、onError、download、條件與迴圈在 M7 加入（路線圖 v2）；
iframe 在 M7a 以定位器的 frame 支援（見 locators.py）；新分頁（彈出視窗）在 M7b 以步驟的
``popup``（這一步開出新分頁，取個名稱）與 ``page``（在哪個分頁執行）支援，
名稱的前後關係在 checks.py 檢查；上傳檔案在 M7c 以 ``upload`` 步驟與 ``type: file`` 的入參支援；
下載檔案以 ``download`` 步驟支援（ADR 0020），檔案存到共用工作資料夾，事實可以當 file 出參。
"""

import re
from collections.abc import Iterable
from typing import Annotated, Final, Literal, Self

from pydantic import BeforeValidator, Field, model_validator

from rpa_core.dsl.fields import (
    ABSOLUTE_URL,
    DslModel,
    FileName,
    Identifier,
    NonEmptyStr,
    OneOrMany,
    Slug,
    TimeoutMs,
    dsl_error,
    join_names,
)
from rpa_core.dsl.locators import Locator

__all__ = [
    "ACTIONS",
    "FACT_ACTIONS",
    "CheckStep",
    "ClickStep",
    "DownloadStep",
    "ExpectStep",
    "ExtractField",
    "ExtractStep",
    "FillStep",
    "GotoStep",
    "Match",
    "PressStep",
    "ScreenshotStep",
    "SelectStep",
    "Step",
    "StepBase",
    "UploadStep",
    "WaitForStep",
    "fact_name",
    "upload_input_names",
]

Match = Literal["contains", "equals", "regex"]
"""字串比對方式：包含（預設）、完全相等、正規表示式（Python re 語法）。"""

LoadState = Literal["load", "domcontentloaded", "networkidle"]


def _require_one(
    model: DslModel, fields: Iterable[tuple[str, str]], *, required: bool = True
) -> str | None:
    """欄位中恰好（或至多）有一個被指定，回傳被指定的 DSL 欄位名稱。

    ``fields`` 是 (Python 屬性名稱, DSL 欄位名稱) 的序列。
    """
    names = list(fields)
    used = [alias for attr, alias in names if getattr(model, attr) is not None]
    if len(used) > 1:
        raise dsl_error("one_of.many", at=[used[1]], fields=join_names(used))
    if not used:
        if required:
            raise dsl_error("one_of.none", fields=join_names(alias for _, alias in names))
        return None
    return used[0]


def _check_regex(pattern: str | None, field: str) -> None:
    if pattern is None:
        return
    try:
        re.compile(pattern)
    except re.error as error:
        raise dsl_error("regex.invalid", at=[field], detail=str(error)) from error


class StepBase(DslModel):
    """所有步驟的共同欄位。"""

    id: Slug
    """場景內唯一的步驟 id；執行結果、截圖與日誌依此歸檔。"""
    name: NonEmptyStr | None = None
    """給人看的說明。"""
    timeout: TimeoutMs | None = None
    """這一步的逾時（毫秒）；沒寫就用場景的 defaults.timeout。"""
    page: Identifier | None = None
    """在哪個分頁執行（M7b）：前面某一步用 popup 開出來的分頁名稱；沒寫是一開始的分頁。"""


class GotoStep(StepBase):
    """開啟網址。"""

    action: Literal["goto"]
    url: NonEmptyStr
    """http(s) 網址；以 / 開頭時接在 browser.baseUrl 後面。"""
    wait_until: Literal["load", "domcontentloaded", "networkidle", "commit"] = "load"
    """等到哪個載入階段才算完成。"""

    @model_validator(mode="after")
    def _check(self) -> Self:
        url = self.url
        if "{{" in url or url == "about:blank" or url.startswith("/"):
            return self
        if not ABSOLUTE_URL.fullmatch(url):
            raise dsl_error("url.invalid", at=["url"], value=url)
        return self


class ClickStep(StepBase):
    """點擊元素。"""

    action: Literal["click"]
    target: Locator
    button: Literal["left", "right", "middle"] = "left"
    click_count: Annotated[int, Field(ge=1, le=3)] = 1
    """1 是單擊，2 是雙擊。"""
    modifiers: list[Literal["Alt", "Control", "ControlOrMeta", "Meta", "Shift"]] | None = None
    """點擊時同時按住的按鍵。"""
    popup: Identifier | None = None
    """這一步會開出新分頁（彈出視窗，M7b）：等它開好，叫做這個名稱；之後的步驟用 page 指定它。"""


class FillStep(StepBase):
    """清空輸入框後填入文字。"""

    action: Literal["fill"]
    target: Locator
    value: str
    """要填入的文字；空字串代表清空。數字要加引號。"""
    popup: Identifier | None = None
    """這一步會開出新分頁（彈出視窗，M7b）：等它開好，叫做這個名稱；之後的步驟用 page 指定它。"""


class SelectStep(StepBase):
    """選擇下拉選單的選項。"""

    action: Literal["select"]
    target: Locator
    option: OneOrMany
    """選項的值或顯示文字；寫成清單代表多選。"""
    popup: Identifier | None = None
    """這一步會開出新分頁（彈出視窗，M7b）：等它開好，叫做這個名稱；之後的步驟用 page 指定它。"""


class CheckStep(StepBase):
    """勾選或取消勾選核取方塊、選項按鈕；已經是指定的狀態時不動作（不像 click 會切換）。"""

    action: Literal["check"]
    target: Locator
    checked: bool = True
    """true 勾選、false 取消勾選。"""
    popup: Identifier | None = None
    """這一步會開出新分頁（彈出視窗，M7b）：等它開好，叫做這個名稱；之後的步驟用 page 指定它。"""


class PressStep(StepBase):
    """按鍵或組合鍵。"""

    action: Literal["press"]
    key: NonEmptyStr
    """Playwright 的按鍵寫法，例如 Enter、Tab、Control+A。"""
    target: Locator | None = None
    """先聚焦到這個元素再按；沒寫就送給目前聚焦的元素。"""
    popup: Identifier | None = None
    """這一步會開出新分頁（彈出視窗，M7b）：等它開好，叫做這個名稱；之後的步驟用 page 指定它。"""


class WaitForStep(StepBase):
    """等待條件成立：元素狀態、網址或頁面載入狀態，三選一。"""

    action: Literal["waitFor"]
    target: Locator | None = None
    state: Literal["visible", "hidden", "attached", "detached"] = "visible"
    """搭配 target：等元素出現、消失、加入或移出 DOM。"""
    url: NonEmptyStr | None = None
    """等網址符合（比對方式見 match）。"""
    match: Match = "contains"
    load_state: LoadState | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        used = _require_one(
            self, [("target", "target"), ("url", "url"), ("load_state", "loadState")]
        )
        if "state" in self.model_fields_set and used != "target":
            raise dsl_error("field.requires", at=["state"], field="state", other="target")
        if "match" in self.model_fields_set and used != "url":
            raise dsl_error("field.requires", at=["match"], field="match", other="url")
        if self.match == "regex":
            _check_regex(self.url, "url")
        return self


_ELEMENT_CHECKS: Final = (
    ("state", "state"),
    ("text", "text"),
    ("value", "value"),
    ("count", "count"),
)
_PAGE_CHECKS: Final = (("url", "url"), ("title", "title"))


class ExpectStep(StepBase):
    """斷言：條件不成立時這一步失敗（會等到 timeout 才判定）。

    有 target 時檢查元素：state、text、value、count 其一；
    沒有 target 時檢查頁面：url、title 其一。
    """

    action: Literal["expect"]
    target: Locator | None = None
    state: (
        Literal["visible", "hidden", "enabled", "disabled", "checked", "unchecked", "editable"]
        | None
    ) = None
    text: str | None = None
    """元素的文字。"""
    value: str | None = None
    """輸入框的值。"""
    count: Annotated[int, Field(ge=0)] | None = None
    """符合定位器的元素個數。"""
    url: str | None = None
    title: str | None = None
    match: Match = "contains"
    """text、value、url、title 的比對方式。"""

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.target is not None:
            for attr, alias in _PAGE_CHECKS:
                if getattr(self, attr) is not None:
                    raise dsl_error("expect.page_check_with_target", at=[alias], field=alias)
            used = _require_one(self, _ELEMENT_CHECKS)
        else:
            for attr, alias in _ELEMENT_CHECKS:
                if getattr(self, attr) is not None:
                    raise dsl_error("field.requires", at=[alias], field=alias, other="target")
            used = _require_one(self, _PAGE_CHECKS)
        if "match" in self.model_fields_set and used in ("state", "count"):
            raise dsl_error("expect.match_not_applicable", at=["match"], field=used)
        if self.match == "regex" and used is not None:
            _check_regex(getattr(self, used), used)
        return self


ExtractGet = Literal["text", "value", "html", "attribute"]


def _check_attribute(model: "ExtractField | ExtractStep", get: str | None) -> None:
    if get == "attribute" and model.attribute is None:
        raise dsl_error("extract.attribute_required")
    if get != "attribute" and model.attribute is not None:
        raise dsl_error(
            "field.requires", at=["attribute"], field="attribute", other="get: attribute"
        )


class ExtractField(DslModel):
    """extract 的 fields 中的一個欄位：相對於每個符合元素的子元素。"""

    target: Locator | None = None
    """在元素裡面找；沒寫就是元素本身。"""
    get: ExtractGet = "text"
    attribute: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        _check_attribute(self, self.get)
        return self


class ExtractStep(StepBase):
    """從頁面抽取資料，存成變數。

    - 預設抽取第一個符合元素的文字；``multiple: true`` 抽取全部，得到清單。
    - ``fields``：每個元素抽成一筆記錄（例如表格的每一列）。
    - ``get: table``：把 <table> 依表頭轉成記錄清單。
    """

    action: Literal["extract"]
    target: Locator
    as_: Identifier = Field(alias="as")
    """存成頁面事實 ``facts.名稱``，之後的步驟、verify 與 outputs 可以引用。"""
    get: Literal["text", "value", "html", "attribute", "table"] = "text"
    attribute: NonEmptyStr | None = None
    """get 為 attribute 時，要讀的屬性名稱，例如 href。"""
    multiple: bool = False
    fields: Annotated[dict[Identifier, ExtractField], Field(min_length=1)] | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.fields is not None and "get" in self.model_fields_set:
            raise dsl_error("extract.fields_with_get", at=["get"])
        if self.get == "table":
            for attr in ("multiple", "attribute"):
                if attr in self.model_fields_set:
                    raise dsl_error("extract.table_conflict", at=[attr], field=attr)
        _check_attribute(self, self.get)
        return self


class ScreenshotStep(StepBase):
    """截圖存為產物。"""

    action: Literal["screenshot"]
    file: FileName | None = None
    """產物檔名（不含副檔名）；沒寫就用步驟 id。name 是步驟說明，不是檔名。"""
    target: Locator | None = None
    """只截這個元素；沒寫就截整個視窗。"""
    full_page: bool = False
    """截整個可捲動的頁面，而不只是視窗範圍。"""

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.full_page and self.target is not None:
            raise dsl_error("screenshot.full_page_with_target", at=["fullPage"])
        return self


_UPLOAD_REFERENCE: Final = re.compile(r"\{\{\s*inputs\.([A-Za-z_][A-Za-z0-9_]{0,63})\s*\}\}")
"""``files`` 的每一項：整個值只有一個 ``{{ inputs.名稱 }}``。"""


def _upload_files(value: object) -> object:
    """``files`` 可以寫一個或一串引用；單一字串視為只有一項的清單（空清單代表清空）。"""
    if isinstance(value, str):
        return [value]
    return value


def upload_input_names(files: Iterable[str]) -> list[str]:
    """``files`` 引用的入參名稱（寫法不對的略過；校驗另外會指出）。"""
    names: list[str] = []
    for item in files:
        match = _UPLOAD_REFERENCE.fullmatch(item.strip())
        if match is not None:
            names.append(match.group(1))
    return names


class UploadStep(StepBase):
    """把檔案交給網頁的上傳框（M7c）。

    檔案一律來自 ``type: file`` 的入參（場景契約的一部分，執行時可以換檔）。三種方式選一種：

    - ``target``：上傳框本身 ``<input type=file>``（隱藏的也可以，不檢查可見性）。最常用。
    - ``trigger``：點了會開出「選擇檔案」視窗的元素。給點擊時才臨時建立上傳框的元件。
    - ``dropzone``：只能拖拽、沒有上傳框的元件：把檔案拖放到這個元素上（檔案合計 20 MB 內）。

    ``upload`` 在檔案交給網頁時就算完成；網頁送到伺服器要多久不一定，之後請用 waitFor／expect
    等畫面上的結果。
    """

    action: Literal["upload"]
    target: Locator | None = None
    trigger: Locator | None = None
    dropzone: Locator | None = None
    files: Annotated[
        list[str], BeforeValidator(_upload_files, json_schema_input_type=str | list[str])
    ]
    """要交的檔案：``{{ inputs.名稱 }}``（type: file 的入參），多個入參寫清單；
    ``[]`` 清空已選的檔案。"""

    @model_validator(mode="after")
    def _check(self) -> Self:
        used = _require_one(
            self, [("target", "target"), ("trigger", "trigger"), ("dropzone", "dropzone")]
        )
        for index, item in enumerate(self.files):
            if _UPLOAD_REFERENCE.fullmatch(item.strip()) is None:
                raise dsl_error("upload.files_format", at=["files", index], value=item)
        if not self.files and used != "target":
            raise dsl_error("upload.clear_requires_target", at=["files"])
        return self


class DownloadStep(StepBase):
    """點擊並等待下載（ADR 0020）。

    檔案存到共用工作資料夾的 ``downloads/``（單獨執行時是這次執行的暫存資料夾），事實
    ``facts.名稱`` 是 ``{"workspace", "name", "size", "sha256"}``：出參寫
    ``{ type: file, from: '{{ facts.名稱 }}' }`` 就能交給下游的 Python 節點或上傳步驟，也會出現在
    報告的產出檔案。下載完成才算這一步完成。
    """

    action: Literal["download"]
    target: Locator
    """點了會開始下載的元素（按鈕、連結）。"""
    as_: Identifier = Field(alias="as")
    """存成頁面事實 ``facts.名稱``。"""
    file_name: NonEmptyStr | None = None
    """存檔的檔名；沒寫用網站給的檔名。可以用 ``{{ }}``，例如 ``報表-{{ inputs.month }}.xlsx``。"""


Step = Annotated[
    GotoStep
    | ClickStep
    | FillStep
    | SelectStep
    | CheckStep
    | PressStep
    | WaitForStep
    | ExpectStep
    | ExtractStep
    | ScreenshotStep
    | UploadStep
    | DownloadStep,
    Field(discriminator="action"),
]
"""任一種步驟，依 action 區分。"""

ACTIONS: Final = (
    "goto",
    "click",
    "fill",
    "select",
    "check",
    "press",
    "waitFor",
    "expect",
    "extract",
    "screenshot",
    "upload",
    "download",
)
"""支援的動作。"""

FACT_ACTIONS: Final = ("extract", "download")
"""會產生頁面事實（``as``）的動作。"""


def fact_name(step: object) -> str | None:
    """這一步產生的頁面事實名稱（extract、download 的 ``as``）；其他步驟是 None。"""
    if getattr(step, "action", None) in FACT_ACTIONS:
        name = getattr(step, "as_", None)
        return name if isinstance(name, str) else None
    return None
