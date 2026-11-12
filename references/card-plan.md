# 临时卡片计划

此文件说明供 Codex 编写计划，不是用户需要手填的表格。实际计划放在每次任务的专用临时目录，打包后删除；最终只交付 `.apkg`。

```json
{
  "source_id": "dcf-obgyn-ed6",
  "deck": "妇产::女性生殖系统生理",
  "scope": {
    "label": "第二章-女性生殖系统生理",
    "pages": [8, 9, 10, 11, 12, 13, 14],
    "confirmed": true
  },
  "cards": [
    {
      "id": "example-bold-body",
      "kind": "cloze",
      "text": "示例正文：{{c1::原加粗片段}}。"
    },
    {
      "id": "example-term",
      "kind": "term",
      "front": "example term",
      "back": "<b>示例术语</b><br>从所选原文整理的中文解释。"
    },
    {
      "id": "example-essay",
      "kind": "essay",
      "front": "简述某红色主题的主要变化。",
      "back": "<ol><li>由对应原页整理的第一点。</li><li>由对应原页整理的第二点。</li></ol>"
    }
  ]
}
```

上例只演示结构，不是完整的制卡内容或医学结论模板。真正内容必须来自此次确认范围。

- 顶层只允许 `source_id`、`deck`、`scope`、`cards`。`scope.pages`为排序且不重复的PDF页序号，非印刷页码。
- `source_id`识别书名和版本，不使用机器绝对路径或整本PDF哈希；`scope.label`识别固定章节或小节。相同内容更新保持它们稳定。
- `card.id`在计划中唯一且跨更新稳定，用简短语义ID。即使调整题干/答案也复用原ID，不按本次排序随意改号。
- 所有卡片只允许上例相应字段。禁止加入tags、Extra、Source、页码或核对说明字段。标题不放入cards。
- 填空 `text` 是纯文本，打包器会转义 `<`、`>`、`&`，防止诸如 `雌激素<200pg/ml` 被当作HTML丢失。每条笔记从c1开始，编号连续且每号只出现一次；不支持hint语法或嵌套花括号。换行转成br。
- 名词解释的front只有英文名词（可有常规连字符、括号、缩写）；禁止中文提示。back先写中文译名，再写解释，不写“来源”“原文英文”等附注。
- 问答front是纯文本，back是简单HTML。支持 `b/strong/i/em/p/div/br/ol/ul/li/table/thead/tbody/tr/th/td/sub/sup`；只允许td/th的数字colspan/rowspan属性。不允许脚本、样式、小字、远程图片或链接；表格文字比较符请写成 `&lt;`、`&gt;`。
- 可以只有某一或两种题型：若确认范围内没有对应标记，不为凑齐三类题型虚构内容。空计划报错。
- 章节边界、正文覆盖、英文术语和答案语义由Codex对照原PDF负责；打包器无法从 `confirmed` 或结构字段证明人类已确认，也不能自动判断任意文字是否为标题。

生成 `.apkg` 后只输出简短数量到终端，不写报告。保留相同计划ID可使Anki识别重复导入；若全部删除了临时计划，再次转换时应复用相同语义ID。删除题目不会自动从Anki中删除原卡。
