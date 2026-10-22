"""錄製稿轉換：codegen 的 Python → DSL 草稿。不需要瀏覽器。"""

from datetime import UTC, datetime
from textwrap import dedent
from typing import cast

import pytest

from rpa_core.dsl import validate_text
from rpa_core.dsl.dynamic import evaluate
from rpa_core.i18n import use_locale
from rpa_core.recording import Conversion, ConversionError, convert_recording, mask_source

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)

SYNC = dedent(
    """\
    import re
    from playwright.sync_api import Playwright, sync_playwright, expect


    def run(playwright: Playwright) -> None:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("http://127.0.0.1:8765/")
        page.get_by_label("標題").click()
        page.get_by_label("標題").fill("示範紀錄")
        page.get_by_label("數量").fill("3")
        page.get_by_role("button", name="建立紀錄").click()
        expect(page.locator("#record-status")).to_contain_text("已建立")
        page.get_by_role("link", name="查詢紀錄").click()
        page.locator("#lookup-id").fill("DEMO-1")
        page.locator("#lookup-id").press("Enter")
        page.close()

        # ---------------------
        context.close()
        browser.close()


    with sync_playwright() as playwright:
        run(playwright)
    """
)


def convert(
    source: str,
    *,
    scene_id: str = "rec-demo",
    url: str | None = None,
    engine: str | None = None,
    role: str | None = None,
    category: str | None = None,
) -> tuple[dict[str, object], Conversion]:
    with use_locale("zh-Hant"):
        result = convert_recording(
            source,
            scene_id=scene_id,
            name="錄製的範例",
            url=url,
            engine=engine,
            role=role,
            category=category,
            now=NOW,
        )
    checked = validate_text(result.scenario)
    assert checked.scenario is not None, checked.issues
    return checked.scenario.model_dump(mode="json", by_alias=True, exclude_none=True), result


def steps_of(data: dict[str, object]) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", data["steps"])


@pytest.mark.parametrize("text", ["{{today}}", "{{customer.name}}", "{{", '{{"{{"}}today}}'])
def test_recorded_input_text_is_preserved_literally(text: str) -> None:
    source = f'page.goto("https://example.test/")\npage.get_by_label("Template").fill({text!r})'
    data, result = convert(source)
    assert not result.warnings
    inputs = cast("dict[str, dict[str, object]]", data["inputs"])
    spec = next(iter(inputs.values()))
    assert evaluate(spec["default"], now=NOW) == text


def test_sync_recording_becomes_a_valid_draft() -> None:
    data, result = convert(SYNC, engine="chromium")

    steps = steps_of(data)
    assert [step["action"] for step in steps] == [
        "goto",
        "click",
        "fill",
        "fill",
        "click",
        "expect",
        "extract",
        "click",
        "fill",
        "press",
    ]
    assert steps[0]["url"] == "/"
    assert data["browser"] == {
        "engine": "chromium",
        "headless": True,
        "baseUrl": "http://127.0.0.1:8765",
    }
    # 先點擊再填寫同一個欄位：兩步都保留（點擊可能展開選單或載入候選，見 _fill）
    assert steps[1]["target"] == steps[2]["target"] == {"label": "標題"}
    assert steps[4]["target"] == {"role": "button", "name": "建立紀錄"}
    # assert text：等內容出現、讀成頁面事實，成為出參，並在獨立斷言檢查有取得內容
    assert steps[5] == {
        "id": "expect-6",
        "name": "確認「#record-status」",
        "action": "expect",
        "target": {"css": "#record-status"},
        "state": "visible",
        "match": "contains",
    }
    assert steps[6] == {
        "id": "extract-7",
        "name": "讀取「#record-status」",
        "action": "extract",
        "target": {"css": "#record-status"},
        "as": "recordStatus",
        "get": "text",
        "multiple": False,
    }
    assert data["outputs"] == {
        "recordStatus": {
            "type": "string",
            "description": "「#record-status」的內容（錄製時是「已建立」）",
            "from": "{{ facts.recordStatus }}",
        }
    }
    assert data["verify"] == [
        {
            "name": "取得「#record-status」（錄製時是「已建立」）",
            "value": "{{ facts.recordStatus }}",
            "notEmpty": True,
        }
    ]
    assert result.outputs == ("recordStatus",)
    assert result.warnings == ()


def test_fill_values_become_inputs_with_recorded_defaults() -> None:
    data, result = convert(SYNC)

    inputs = data["inputs"]
    assert inputs == {
        "field": {"type": "string", "description": "標題", "default": "示範紀錄"},
        "field_2": {"type": "string", "description": "數量", "default": "3"},
        "lookup_id": {"type": "string", "description": "#lookup-id", "default": "DEMO-1"},
    }
    assert steps_of(data)[2]["value"] == "{{ inputs.field }}"
    assert result.inputs == ("field", "field_2", "lookup_id")


def test_typing_key_by_key_becomes_fill_with_a_warning() -> None:
    source = dedent(
        """\
        page.goto("https://erp.example.com/")
        page.get_by_placeholder("搜尋").press_sequentially("455590002")
        page.get_by_label("備註").type("急件")
        page.get_by_label("數量").fill("3")
        """
    )
    data, result = convert(source)

    assert [step["action"] for step in steps_of(data)] == ["goto", "fill", "fill", "fill"]
    # 逐鍵的事件不會重現：兩行都列警告，直接 fill 的不列
    assert [(warning.line, warning.message) for warning in result.warnings] == [
        (
            2,
            "press_sequentially 是逐字輸入，轉成 fill（一次填入整段文字），不會觸發每個按鍵的事件；"
            "欄位要靠按鍵才有反應（例如邊打邊搜尋）時，調試時請確認",
        ),
        (
            3,
            "type 是逐字輸入，轉成 fill（一次填入整段文字），不會觸發每個按鍵的事件；"
            "欄位要靠按鍵才有反應（例如邊打邊搜尋）時，調試時請確認",
        ),
    ]


def test_password_fields_become_secrets_and_are_masked() -> None:
    source = dedent(
        """\
        page.goto("https://erp.example.com/login")
        page.get_by_placeholder("Password").fill("s3cret-pass")
        page.get_by_label("密碼").type("another-secret")
        page.locator("#username").fill("alice")
        """
    )
    data, result = convert(source, scene_id="erp-login")

    assert data["secrets"] == ["ERP_LOGIN_PASSWORD", "ERP_LOGIN_PASSWORD_2"]
    steps = steps_of(data)
    assert steps[1]["value"] == "{{ secrets.ERP_LOGIN_PASSWORD }}"
    assert steps[2]["value"] == "{{ secrets.ERP_LOGIN_PASSWORD_2 }}"
    assert data["inputs"] == {
        "username": {"type": "string", "description": "#username", "default": "alice"}
    }
    masked = result.masked_source
    assert "s3cret-pass" not in masked
    assert "another-secret" not in masked
    assert 'fill("***")' in masked
    assert "alice" in masked
    assert "s3cret" not in result.scenario


def test_password_on_unsupported_line_is_masked_in_comments() -> None:
    source = dedent(
        """\
        page.goto("https://erp.example.com/login")
        page1 = context.new_page()
        page1.get_by_label("Password").fill("top-secret")
        """
    )
    data, result = convert(source)

    assert len(steps_of(data)) == 1
    assert "top-secret" not in result.scenario
    assert "top-secret" not in result.masked_source
    assert "page1" in result.warnings[0].message


def test_iframe_elements_get_a_frame_locator() -> None:
    """codegen 的兩種 iframe 寫法（frame_locator、content_frame）與巢狀 iframe 都轉成 frame。"""
    source = dedent(
        """\
        page.goto("https://erp.example.com/login")
        page.frame_locator("#login").get_by_label("Account").fill("alice")
        page.frame_locator("#login").get_by_label("Password").fill("top-secret")
        page.locator("iframe[name=\\"m\\"]").content_frame.get_by_role("button", name="Go").click()
        page.locator("#app").content_frame.locator("iframe").first.content_frame.get_by_text("Done").click()
        page.frame_locator("iframe").nth(1).locator("form").get_by_role("button").click()
        page.locator("#panel").frame_locator("iframe").get_by_text("OK").click()
        expect(page.locator("#report").content_frame.locator("#total")).to_contain_text("42")
        """
    )
    data, result = convert(source)

    steps = steps_of(data)
    assert [step.get("target") for step in steps[1:7]] == [
        {"label": "Account", "frame": {"css": "#login"}},
        {"label": "Password", "frame": {"css": "#login"}},
        {"role": "button", "name": "Go", "frame": {"css": 'iframe[name="m"]'}},
        {"text": "Done", "frame": {"css": "iframe", "nth": 0, "frame": {"css": "#app"}}},
        {"role": "button", "within": {"css": "form"}, "frame": {"css": "iframe", "nth": 1}},
        {"text": "OK", "frame": {"css": "iframe", "within": {"css": "#panel"}}},
    ]
    # 密碼欄位照樣改成 Secret；欄位在 iframe 裡也一樣
    assert steps[2]["value"] == "{{ secrets.REC_DEMO_PASSWORD }}"
    assert "top-secret" not in result.scenario
    assert "top-secret" not in result.masked_source
    # assert text 在 iframe 裡：等出現、抽取、出參
    assert [step["action"] for step in steps[7:]] == ["expect", "extract"]
    assert steps[8]["target"] == {"css": "#total", "frame": {"css": "#report"}}
    assert result.outputs == ("total",)
    assert result.warnings == ()


def test_frame_locator_without_selector_becomes_any_frame() -> None:
    """codegen 1.63 起，兩層以上的 iframe 錄成開頭不帶引數的 frame_locator()（在任何 iframe 裡找）。

    錄製稿取自測試網站 /frames 的人工驗收（Firefox，2026-10-21）。
    """
    form = 'page.locator("iframe[title=\\"紀錄表單\\"]").content_frame'
    note = 'locator("iframe[title=\\"確認事項\\"]")'
    source = "\n".join(
        [
            'page.goto("http://127.0.0.1:8765/frames")',
            f'{form}.get_by_role("textbox", name="標題").fill("标题一")',
            'page.frame_locator().get_by_role("checkbox", name="我已確認").check()',
            f"{form}.{note}.click()",
            f'page.frame_locator().{note}.content_frame.get_by_text("我已確認").click()',
            'page.frame_locator().locator("form").get_by_role("button", name="送出").click()',
        ]
    )
    data, result = convert(source)

    steps = steps_of(data)
    form = {"css": 'iframe[title="紀錄表單"]'}
    assert [step["target"] for step in steps[1:]] == [
        {"role": "textbox", "name": "標題", "frame": form},
        {"role": "checkbox", "name": "我已確認", "anyFrame": True},
        {"css": 'iframe[title="確認事項"]', "frame": form},
        {"text": "我已確認", "frame": {"css": 'iframe[title="確認事項"]', "anyFrame": True}},
        {"role": "button", "name": "送出", "within": {"css": "form"}, "anyFrame": True},
    ]
    assert steps[2]["action"] == "check"
    # 點擊 iframe 元素本身：保留這一步，但提醒確認
    assert [warning.line for warning in result.warnings] == [4]
    assert 'iframe[title="確認事項"]' in result.warnings[0].message


def test_iframe_chains_that_cannot_be_converted() -> None:
    source = dedent(
        """\
        page.goto("https://erp.example.com/")
        page.frame_locator(selector).get_by_text("OK").click()
        page.locator("#a").content_frame.click()
        page.get_by_text("A").frame_locator().get_by_text("B").click()
        """
    )
    _, result = convert(source)

    assert [warning.line for warning in result.warnings] == [2, 3, 4]


def test_unsupported_lines_stay_as_comments_with_warnings() -> None:
    source = dedent(
        """\
        page.goto("http://127.0.0.1:8765/")
        page.get_by_text("選單").hover()
        page1 = context.new_page()
        page1.goto("http://127.0.0.1:8765/help")
        page1.get_by_role("button", name="關閉").click()
        page.locator("#file").set_input_files("a.txt")
        """
    )
    data, result = convert(source)

    # 自己開的新分頁（context.new_page）還不支援；錄到的新分頁（expect_popup）見下面的測試
    assert [step["action"] for step in steps_of(data)] == ["goto"]
    warnings = result.warnings
    assert [warning.line for warning in warnings] == [2, 4, 5, 6]
    assert warnings[0].source == 'page.get_by_text("選單").hover()'
    text = result.scenario
    assert "# 錄製稿第 2 行轉不了" in text
    assert '#   page.get_by_text("選單").hover()' in text
    assert "有 4 行轉不了" in text


def test_actions_on_a_popup_tab_get_page() -> None:
    """M7b：使用者驗收時的錄製稿（點擊開出新分頁 page1，在 page1 新增商品行）。"""
    row = 'page1.get_by_role("row", name="  -- --", exact=True)'
    source = "\n".join(
        [
            'page.goto("https://erp.example.com/orders")',
            "with page.expect_popup() as page1_info:",
            '    page.get_by_role("link", name="SO-1001").click()',
            "page1 = page1_info.value",
            'page1.once("dialog", lambda dialog: dialog.dismiss())',
            'page1.get_by_role("button", name=" 新增商品行").click()',
            f'{row}.get_by_placeholder("请选择").click()',
            f'{row}.get_by_placeholder("请选择").fill("455590002")',
            'expect(page1.get_by_role("status")).to_contain_text("已儲存")',
            'expect(page1).to_have_url("https://erp.example.com/orders/1/items")',
            "page1.close()",
            'page.get_by_role("button", name="重新整理").click()',
        ]
    )
    data, result = convert(source)

    assert result.warnings == ()
    steps = steps_of(data)
    assert [(step["action"], step.get("page"), step.get("popup")) for step in steps] == [
        ("goto", None, None),
        ("click", None, "page1"),
        ("click", "page1", None),
        # 先點「请选择」再填：點擊會展開選單、載入候選，保留；兩步都在 page1
        ("click", "page1", None),
        ("fill", "page1", None),
        ("expect", "page1", None),
        ("extract", "page1", None),
        ("expect", "page1", None),
        ("click", None, None),
    ]
    choose = {"placeholder": "请选择", "within": {"role": "row", "name": "  -- --", "exact": True}}
    assert steps[3]["target"] == steps[4]["target"] == choose
    assert steps[4]["value"] == "{{ inputs.field }}"
    assert steps[7]["url"] == "/orders/1/items"
    # YAML 裡 page 緊接在 action 後面，popup 在最後
    assert "    action: click\n    page: page1\n" in result.scenario
    assert "    popup: page1\n" in result.scenario


def test_popups_from_popups_and_popups_that_cannot_be_converted() -> None:
    source = dedent(
        """\
        page.goto("https://erp.example.com/")
        with page.expect_popup() as page1_info:
            page.get_by_text("明細").click()
        page1 = page1_info.value
        with page1.expect_popup() as page2_info:
            page1.get_by_text("列印").click()
        page2 = page2_info.value
        page2.get_by_role("button", name="確定").click()
        with page.expect_popup() as page3_info:
            page.get_by_text("說明").hover()
        page3 = page3_info.value
        page3.get_by_text("x").click()
        page9.get_by_text("y").click()
        """
    )
    data, result = convert(source)

    steps = steps_of(data)
    assert [(step.get("page"), step.get("popup")) for step in steps[1:]] == [
        (None, "page1"),
        ("page1", "page2"),
        ("page2", None),
    ]
    # hover 轉不了 → 開出 page3 的那一步沒有了；page3、不認得的 page9 上的操作都略過
    assert sorted(warning.line for warning in result.warnings) == [9, 10, 12, 13]


def test_continue_recording_after_a_popup() -> None:
    """接著既有場景錄製：新的分頁名稱避開既有的；既有步驟開過的分頁 codegen 叫 page1，轉不了。"""
    existing_text = dedent(
        """\
        schemaVersion: 1
        id: rec-demo
        name: 既有場景
        steps:
          - id: open
            action: goto
            url: https://erp.example.com/
          - id: open-items
            action: click
            target: { text: 明細 }
            popup: page1
        """
    )
    existing = validate_text(existing_text).scenario
    assert existing is not None
    source = dedent(
        """\
        page1.get_by_text("儲存").click()
        with page.expect_popup() as page1_info:
            page.get_by_text("說明").click()
        page1 = page1_info.value
        page1.get_by_text("關閉").click()
        """
    )
    with use_locale("zh-Hant"):
        result = convert_recording(
            source, scene_id="rec-demo", name="既有場景", existing=existing, prepend_goto=False
        )
    assert [warning.line for warning in result.warnings] == [1]
    text = "\n".join(result.parts.step_lines if result.parts else ())
    assert "popup: page1_2" in text
    assert "page: page1_2" in text


def test_locator_variants() -> None:
    source = dedent(
        """\
        page.goto("http://127.0.0.1:8765/")
        page.get_by_role("cell", name="已建立", exact=True).click()
        page.get_by_text("下一頁").first.click()
        page.get_by_role("row").nth(2).click()
        page.locator("div").filter(has_text=re.compile(r"^記住我$")).get_by_role("checkbox").check()
        page.get_by_test_id("agree").uncheck()
        page.locator("li").filter(has_text="訂單").last.click()
        page.locator("xpath=//button[1]").dblclick()
        page.get_by_role("combobox").select_option(["a", "b"])
        page.get_by_text(re.compile(r"^完成$")).click(button="right")
        expect(page.get_by_role("checkbox")).to_be_checked()
        expect(page.locator("#name")).to_have_value("小明")
        expect(page).to_have_url("http://127.0.0.1:8765/done")
        """
    )
    data, result = convert(source)

    steps = steps_of(data)
    assert [step["target"] for step in steps[1:9]] == [
        {"role": "cell", "name": "已建立", "exact": True},
        {"text": "下一頁", "nth": 0},
        {"role": "row", "nth": 2},
        {"role": "checkbox", "within": {"css": 'div:text-is("記住我")'}},
        {"testId": "agree"},
        {"css": "li", "hasText": "訂單", "nth": -1},
        {"xpath": "//button[1]"},
        {"role": "combobox"},
    ]
    assert steps[4]["action"] == "check"
    assert steps[5]["checked"] is False
    assert steps[7]["clickCount"] == 2
    assert steps[8]["option"] == ["a", "b"]
    assert steps[9]["target"] == {"text": "完成", "exact": True}
    assert steps[9]["button"] == "right"
    assert steps[10]["state"] == "checked"
    # assert value：讀取欄位的值（不用先等出現）
    assert (steps[11]["action"], steps[11]["as"], steps[11]["get"]) == ("extract", "name", "value")
    assert (steps[12]["url"], steps[12]["match"]) == ("/done", "equals")
    assert result.outputs == ("name",)
    assert result.warnings == ()


def test_asserted_text_that_was_typed_is_compared_with_the_input() -> None:
    source = dedent(
        """        page.goto("http://127.0.0.1:8765/")
        page.get_by_role("textbox", name="標題").fill("示範紀錄")
        page.get_by_role("spinbutton", name="數量").fill("12")
        page.get_by_role("button", name="建立紀錄").click()
        expect(page.get_by_test_id("record-title")).to_have_text("示範紀錄")
        expect(page.locator("#record-id")).to_contain_text("DEMO-ABC")
        expect(page.locator("#record-id")).to_contain_text("DEMO-ABC")
        """
    )
    data, result = convert(source)

    # 沒有英數名稱的欄位依角色取名；數字欄位填整數時是 integer
    assert data["inputs"] == {
        "text": {"type": "string", "description": "標題", "default": "示範紀錄"},
        "number": {"type": "integer", "description": "數量", "default": 12},
    }
    assert result.outputs == ("recordTitle", "recordId", "recordId_2")
    verify = cast("list[dict[str, object]]", data["verify"])
    assert verify[0] == {
        "name": "「record-title」與入參 text 相同",
        "value": "{{ facts.recordTitle }}",
        "equals": "{{ inputs.text }}",
    }
    assert verify[1]["notEmpty"] is True


def test_async_and_pytest_styles() -> None:
    asynchronous = dedent(
        """\
        async def run(playwright):
            page = await context.new_page()
            await page.goto("https://example.com/")
            await page.get_by_role("link", name="More").click()
        """
    )
    pytest_style = dedent(
        """\
        def test_example(page: Page) -> None:
            page.goto("https://example.com/")
            page.get_by_role("link", name="More").click()
        """
    )
    first, _ = convert(asynchronous)
    second, _ = convert(pytest_style)

    assert steps_of(first) == steps_of(second)
    assert [step["action"] for step in steps_of(first)] == ["goto", "click"]


def test_start_url_used_when_recording_has_no_goto() -> None:
    data, _ = convert('page.get_by_role("button", name="OK").click()\n', url="https://a.example/x")

    steps = steps_of(data)
    assert steps[0]["action"] == "goto"
    assert steps[0]["url"] == "/x"
    assert data["browser"] == {
        "engine": "chromium",
        "headless": True,
        "baseUrl": "https://a.example",
    }


def test_role_and_category_are_written() -> None:
    data, _ = convert(SYNC, role="testsite-user", category="錄製")

    assert data["login"] == {"role": "testsite-user"}
    assert data["category"] == "錄製"


def test_other_origins_stay_absolute() -> None:
    source = 'page.goto("https://a.example/")\npage.goto("https://b.example/next")\n'
    data, _ = convert(source)

    assert [step["url"] for step in steps_of(data)] == ["/", "https://b.example/next"]


def test_errors() -> None:
    with pytest.raises(ConversionError):
        convert_recording("def (", scene_id="x", name="x")
    with pytest.raises(ConversionError):
        convert_recording("print('hello')\n", scene_id="x", name="x")


def test_english_names() -> None:
    with use_locale("en"):
        result = convert_recording(SYNC, scene_id="rec", name="Recorded", now=NOW)
    assert 'name: "Fill in \\"標題\\""' in result.scenario


def test_mask_source_handles_multibyte_columns() -> None:
    source = 'x = "密碼"; page.fill("值")\n'
    start = len('x = "密碼"; page.fill('.encode())
    masked = mask_source(source, [(1, start, 1, start + len('"值"'.encode()))])
    assert masked == 'x = "密碼"; page.fill("***")\n'


EXISTING = dedent(
    """\
    # 既有的場景：註解與寫法都要原樣保留
    schemaVersion: 1
    id: rec-demo
    name: 既有場景

    inputs:
      title: { type: string, default: 舊標題 }

    browser:
      baseUrl: http://127.0.0.1:8765

    steps:
    - id: open
      action: goto
      url: /
    - id: fill-2  # 舊的填寫
      action: fill
      target: { label: 標題 }
      value: "{{ inputs.title }}"
    """
)

CONTINUED = dedent(
    """\
    def run(playwright: Playwright) -> None:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page.get_by_role("textbox", name="title").fill("新標題")
        page.get_by_role("button", name="建立紀錄").click()
        expect(page.locator("#record-id")).to_contain_text("DEMO-1")
        page.close()
    """
)


def test_continue_recording_appends_to_the_existing_scenario() -> None:
    from rpa_core.recording import merge_recording

    existing = validate_text(EXISTING).scenario
    assert existing is not None
    with use_locale("zh-Hant"):
        result = convert_recording(
            CONTINUED,
            scene_id="rec-demo",
            name="既有場景",
            existing=existing,
            prepend_goto=False,
            now=NOW,
        )
        merged = merge_recording(EXISTING, existing, result)

    # 原有內容一字不動，新的內容接在各段落最後
    for line in EXISTING.splitlines():
        assert line in merged.splitlines()
    checked = validate_text(merged)
    assert checked.scenario is not None, checked.issues
    scenario = checked.scenario
    assert [step.id for step in scenario.steps or []] == [
        "open",
        "fill-2",
        "fill-3",
        "click-4",
        "expect-5",
        "extract-6",
    ]
    # 新的入參避開既有的名稱；清單的縮排跟著原本的寫法（項目從第一欄開始）
    assert list(scenario.inputs) == ["title", "title_2"]
    assert "\n- id: fill-3\n" in merged
    assert list(scenario.outputs) == ["recordId"]
    assert scenario.verify is not None
    assert scenario.verify[0].not_empty is True
    assert result.steps == 4


def test_continue_recording_without_new_steps_is_an_error() -> None:
    existing = validate_text(EXISTING).scenario
    assert existing is not None
    with use_locale("zh-Hant"), pytest.raises(ConversionError, match="沒有可以轉換的操作"):
        convert_recording(
            "page.close()\n", scene_id="rec-demo", name="x", existing=existing, prepend_goto=False
        )
