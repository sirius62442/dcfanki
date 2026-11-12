# dcfanki

把戴春峰（DCF）系列医学笔记 PDF 的指定章节、小节或页码范围，转换为可直接导入 Anki 的 `.apkg`。

**每次先确认范围，再制卡。最终只给一个 `.apkg`：不含黑色标题卡、不含标签、不含来源脚注或制卡说明，不附带核对文件。**

## 1. 它如何工作

| PDF标记 | 卡片类型 | 正面 | 背面 |
| --- | --- | --- | --- |
| 黑色加粗正文 | 填空 | 带必要上下文的原文，仅加粗处挖空 | 显示该空答案 |
| 蓝色带下划线术语 | 名词解释 | 只有英文名词 | 中文翻译＋名词解释 |
| 红色主题 | 简答 | 根据对应段落或表格拟定的问题 | 对应内容整理的答案 |

章名、节标题、小节标题、表头或纯结构标签不做黑色填空。表格正文中的加粗重点仍然制卡。红色主题和蓝色术语即使同时加粗，也只做对应颜色的题型，不重复挖空。

长句有多个加粗片段时，每处分别生成一张填空卡；跨行断开的同一个词合并。只有选定范围存在的题型才生成，不为凑齐三类而虚构题目。

这是**由 Codex 执行的 Skill**，不是独立的一键 PDF 转卡工具。格式提取和APKG打包由本地脚本完成；Codex对照原页判断标题、还原表格语境、组织术语解释和简答答案。脚本本身不会自动完成这一步语义工作，也不自行调用外部模型接口。

## 2. 仓库结构

```text
dcfanki/
├── SKILL.md                 Codex的工作指令
├── README.md                本操作说明
├── requirements.txt         Python依赖
├── .gitignore               排除资料、卡包及临时文件
├── agents/
│   └── openai.yaml          Skill显示信息
├── references/
│   └── card-plan.md         临时卡片计划格式
└── scripts/
    ├── extract_pdf.py       仅提取指定页及首尾边界
    ├── build_apkg.py        内置模板、校验并生成APKG
    └── test_dcfanki.py      合成PDF和卡包回归测试
```

原始PDF、真实题库、临时计划、依赖包和测试生成的卡包均不在发布包中。依赖安装后 `.venv` 留在本地，不上传GitHub。

## 3. 本机安装（Windows / PowerShell）

需要 Python 3.10或更高版本，以及能读取本地文件、运行Python并查看PDF页面的Codex环境。以下是一次性安装。

### 方法A：从本地发布包安装

解压发布包后，确认 `dcfanki` 目录中直接有 `SKILL.md`。在PowerShell运行，第一行替换成你解压后的实际路径：

```powershell
$sourceDir = 'E:\Desktop\courses\7\dcfanki'
$skillParent = Join-Path $env:USERPROFILE '.agents\skills'
$skillDir = Join-Path $skillParent 'dcfanki'
if (Test-Path -LiteralPath $skillDir) { throw 'dcfanki已存在，请先确认是否需要更新，不要直接重复覆盖。' }
New-Item -ItemType Directory -Force -Path $skillParent | Out-Null
Copy-Item -LiteralPath $sourceDir -Destination $skillDir -Recurse
```

用户级Skill路径采用 `~/.agents/skills/dcfanki`。Codex也支持项目中的 `.agents/skills`；同名Skill不要同时安装多份，以免选择混淆。路径依据：[官方Skill文档](https://learn.chatgpt.com/docs/build-skills)。

### 方法B：上传GitHub后克隆安装

先完成第7节的上传，再运行；把 `YOUR_USER` 换成GitHub用户名。`skillDir`已存在时不要重复克隆。

```powershell
$skillParent = Join-Path $env:USERPROFILE '.agents\skills'
$skillDir = Join-Path $skillParent 'dcfanki'
New-Item -ItemType Directory -Force -Path $skillParent | Out-Null
git clone https://github.com/YOUR_USER/dcfanki.git "$skillDir"
```

两种安装方法选一种即可。

### 安装依赖并检查

```powershell
$skillDir = Join-Path $env:USERPROFILE '.agents\skills\dcfanki'
python -m venv "$skillDir\.venv"
& "$skillDir\.venv\Scripts\python.exe" -m pip install -r "$skillDir\requirements.txt"
& "$skillDir\.venv\Scripts\python.exe" -m pip check
& "$skillDir\.venv\Scripts\python.exe" -m unittest discover -s "$skillDir\scripts" -p test_dcfanki.py -v
```

不需要激活虚拟环境，避免PowerShell执行策略拦截激活脚本。预期测试显示 `OK`。首次安装需要访问Python包索引下载依赖，之后格式提取和打包均在本地进行。PDF渲染使用Codex环境已有的PDF查看/渲染能力，不需要为本Skill另装OCR服务。

macOS/Linux可将路径换为 `~/.agents/skills/dcfanki`，用 `python3 -m venv`，虚拟环境解释器改为 `.venv/bin/python`。当前发布在Windows上验证，未在其他系统运行。

安装后新建Codex对话，输入 `$dcfanki`。若Skill未出现，重启Codex再检查。安装/发现方式参考[官方文档](https://learn.chatgpt.com/docs/build-skills)；本仓库不声称当前对话已经重新加载了新Skill。

## 4. 日常使用

在能访问PDF的Codex项目中发送：

```text
使用 $dcfanki，把“妇产/17. 妇产科学笔记（戴春峰）（第6版）.pdf”
中的“女性生殖系统生理”做成Anki。
先确认章节和PDF页码范围，最终只给.apkg。
```

也可以只处理更小的范围：

```text
使用 $dcfanki，只转换这个PDF里“卵巢性激素的合成和分泌”这一小节。
先定位小节的起止位置，向我确认，不要处理其他部分。
```

或者直接给PDF页序号：

```text
使用 $dcfanki，处理这个PDF的第20～23页。
第20页从“某节标题”开始，第23页在“下一节标题”之前结束。
先复述范围让我确认。
```

每次流程：

1. Codex先定位，并列出文件、章节/小节、PDF页序号、首页与末页边界。
2. 你回复“确认，就这个范围”之后，才开始该范围的提取和制卡。
3. Codex查看原PDF页面，完成三类题目并打包。
4. 最终给出 `.apkg` 链接和简短卡数，不另外生成说明、标签、预览或核对文件。

**PDF页序号从1开始，不一定等于页面上印的页码。** 一个章节如果只占首页下半部或末页上半部，会按边界裁剪；不会把相邻章节一并转入。确认前只允许为定位查看目录、书签及少量候选边界页，不先转换整本。

如果只说“转这本PDF”，Skill先询问范围。若想整本处理，也需要明确确认整本范围；较长材料可分章逐次确认，不擅自扩展。

## 5. 导入Anki与更新

1. 打开Anki，选择“文件 → 导入”，选择生成的 `.apkg`。
2. 卡包自带笔记类型和正反面模板，不需要映射TSV字段。
3. 导入后，先查看一张填空、一张名词解释和一张简答，确认答案显示正常。

APKG能携带牌组、笔记类型和卡片，参见[Anki官方说明](https://docs.ankiweb.net/manual/importing/packaged-decks)。

如果让Codex修改同一范围的卡片，应说明“更新原卡包，保持source_id、scope.label和原card.id”。Skill使用稳定GUID，帮助Anki识别更新。重新导入时，根据导入界面的选项更新已有笔记/笔记类型；Anki的具体行为受版本和本地修改影响，见[更新规则](https://docs.ankiweb.net/manual/importing/packaged-decks#updating)。

更新不会自动删除以前已导入、后来从卡包中移除的题目。不同历史导出工具生成的旧卡也不保证自动合并；需要时在Anki中自行暂停或删除确认不再需要的旧卡。Skill不直接改动Anki数据库，也不保存或重置学习记录。

## 6. 手动运行脚本（可选，供维护者）

正常使用不需要手动写计划，Codex会执行这部分。这里给出完整命令，便于调试和维护。先安装依赖。

```powershell
$skillDir = Join-Path $env:USERPROFILE '.agents\skills\dcfanki'
$pythonExe = Join-Path $skillDir '.venv\Scripts\python.exe'
$workDir = Join-Path ([System.IO.Path]::GetTempPath()) ('dcfanki-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $workDir | Out-Null
& $pythonExe "$skillDir\scripts\extract_pdf.py" 'E:\资料\笔记.pdf' --pages '8-14' --output "$workDir\candidates.json"
```

这一步只提取指定页面的文字和格式候选，不产生卡片。若章节跨页边界，添加 `--first-top` 和 `--last-bottom`，坐标为PDF点、从页顶向下。不要把其他文件的裁剪数字套用到自己的PDF。

对照原页完成临时 `plan.json`，格式见 [references/card-plan.md](references/card-plan.md)，然后运行：

```powershell
& $pythonExe "$skillDir\scripts\build_apkg.py" "$workDir\plan.json" --output 'E:\导出\章节名.apkg'
```

目标父目录必须已存在。已有同名文件时默认报错；确认是要替换该文件，才在末尾添加 `--replace`。程序先在临时目录中打包和检查，再替换目标，不边写边覆盖旧包。脚本的首末页裁剪仅支持整宽的上下边界；多栏章节起止位置若不能这样表示，应按确认区域视觉读取或先生成临时区域裁剪，不能把相邻栏的内容一并制卡。

`scope.confirmed`仅记录真实的人类确认，不是验证聊天记录的技术机制。直接运行脚本不能替代范围确认或原页视觉复核。临时目录应从创建时起就安排try/finally清理，完成、失败或取消后均删除本次中间资料；强制中断时可能无法立即清理，恢复后只清理该次创建的专用目录。只保留目标 `.apkg`。

## 7. 上传到自己的GitHub

### 方法A：网页上传

1. 在GitHub新建仓库，名称填 `dcfanki`，选择Public或Private。
2. 解压发布包，进入其中 `dcfanki` 文件夹。
3. 在仓库页面选择 **Add file → Upload files**，上传该目录内的文件和子目录。根目录应直接看到 `SKILL.md`、`README.md`、`scripts/`，不要只上传ZIP，也不要无意多套一层 `dcfanki/`。
4. 填写提交说明，例如 `Add dcfanki skill`，提交到仓库。
5. 核对仓库的 `scripts/`、`agents/`、`references/` 均存在；浏览器若未显示隐藏文件，补充上传 `.gitignore`。

网页操作依据：[GitHub上传文件说明](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)。

### 方法B：Git命令上传

先在GitHub创建**空仓库** `dcfanki`（不勾选初始化README、LICENSE、gitignore），本机已安装Git并完成GitHub认证。以下命令在解压后的Skill目录运行；不要在整个课程资料目录执行：

```powershell
Set-Location 'E:\Desktop\courses\7\dcfanki'
git init -b main
git add SKILL.md README.md requirements.txt .gitignore agents scripts references
git status --short
git commit -m 'Add dcfanki skill'
git remote add origin https://github.com/YOUR_USER/dcfanki.git
git push -u origin main
```

把 `YOUR_USER` 替换成你的用户名。若Git要求姓名和邮箱，按其提示配置你希望出现在提交记录中的身份；登录凭证由你在GitHub/Git工具中处理。若已有远程地址或远端并非空仓库，不重复运行这组初始化命令，不使用强制推送。

上传前看 `git status --short`：只应包含上述Skill源码和文档。不要上传自己的PDF、卡包、虚拟环境、临时计划或原始笔记内容。`.gitignore`已忽略常见资料/输出文件。若要明确授权他人复用，可在GitHub添加你选择的LICENSE。

上传完成后的仓库地址应类似：`https://github.com/YOUR_USER/dcfanki`。其他电脑可用第3节的方法B安装。

### 后续维护和升级

修改代码后先运行第3节测试，再 `git add`、`git commit`、`git push`。对通过Git克隆安装的副本，先确认没有需要保留的本地未提交修改，再执行：

```powershell
$skillDir = Join-Path $env:USERPROFILE '.agents\skills\dcfanki'
git -C "$skillDir" pull --ff-only
& "$skillDir\.venv\Scripts\python.exe" -m pip install -r "$skillDir\requirements.txt"
& "$skillDir\.venv\Scripts\python.exe" -m unittest discover -s "$skillDir\scripts" -p test_dcfanki.py -v
```

## 8. 限制和故障处理

| 情况 | 处理 |
| --- | --- |
| 提示找不到pdfminer或genanki | 用Skill自己的 `.venv` 解释器运行，并按requirements安装依赖 |
| Skill列表没有dcfanki | 检查 `~/.agents/skills/dcfanki/SKILL.md` 是否存在；新建对话或重启Codex；避免重复安装 |
| 没给章节就开始转换 | 不符合流程；要求先列出范围并等你确认 |
| 名词卡正面出现中文提示 | 不符合规则；要求仅英文，背面保留中文与解释 |
| 答案不显示 | 确认导入的是APKG，并查看是否更新了笔记类型；Skill内置模板明确引用Back，不依赖手动字段映射 |
| 卡片出现出处、页码、标签或小字 | 不符合规则；要求更新原包去除，保持原ID |
| 看得到粗体但字体名没有Bold | 提取器还检查PDF描边填充模式；仍需回看原页，不能只靠字体名 |
| 蓝字未检出下划线 | 自动下划线检测只是候选，需看原页再决定，不把所有蓝字一概纳入 |
| 扫描页、乱码或只提取少量字 | 报告限制，停止把稀疏输出当成完整转换；不自动付费OCR |
| 表格提取串列 | 以原页恢复行列语境，再组织题干，不直接把串列文本制卡 |

当前已在Windows上验证合成PDF的局部提取、假粗体/颜色/下划线识别、裁剪、卡包答案模板、零标签、稳定GUID及异常输入保护，并回归本次“女性生殖系统生理”样本。尚未逐一验证其他DCF分册/版本，也未在实际Anki客户端导入。不同PDF字体、颜色或扫描方式可能需要调整识别与视觉复核。
