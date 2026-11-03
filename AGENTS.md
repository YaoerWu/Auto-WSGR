# ShiinaSkuya Upgrade Worktree Agent Rules

本文件只适用于当前 worktree 以及在此 worktree 中工作的所有 Codex Agent。

- Task ID: `20260913-shiinaskuya-upgrade-7b3e`
- Branch: `codex/20260913-shiinaskuya-upgrade-7b3e`
- Worktree: `AutoWSGR/.worktrees/ShiinaSkuya-upgrade`

这是临时架构升级 worktree，不是发布分支，也不是兼容迁移分支。系统指令、开发者指令、
安全要求、数据保护要求和用户当前明确要求始终优先于本文件。

## 1. 规则优先级

三层规则叠加生效：`pre-commit` / Ruff 等工具自动结果管**项目整体格式**（最高），根目录
`AGENTS.md` 与本文件管**项目禁止项**，`docs/features/` 下的模块级规范管**项目细节**。
冲突时按此顺序取高优先级者；完整定义见 `docs/features/[规范]python-code-style.md`
1.1 节。

代码改动按以下顺序读取规范：

1. 模块级规范：
   - `docs/features/[规范]python-code-style.md`
   - `docs/features/[规范]ui-code-style.md`
   - `docs/features/[规范]dispatch-context临时规范.md`
2. 架构说明（按主程序目录一一对应，每篇讲清模块定位、依赖、入口出口与维护要点）：
   - `docs/AutoWSGR3.0/README.md`：四层总览与分组索引，先读它
   - `docs/AutoWSGR3.0/common/system.md`
   - `docs/AutoWSGR3.0/common/device.md`
   - `docs/AutoWSGR3.0/common/vision.md`
   - `docs/AutoWSGR3.0/application/navigation/README.md`
   - `docs/AutoWSGR3.0/application/controller/README.md`
   - `docs/AutoWSGR3.0/application/controller/home.md`、`login.md`、`mission.md`、
     `sidebar.md`、`backyard.md`、`sortie.md`、`event.md`：controller 各业务包

模块级规范先于架构说明。出现无法消解的规范冲突时暂停当前改动并报告，不自行猜测。

本 worktree 不默认执行仓库级的发布、提交格式、全量测试、全量 pre-commit、构建、跨仓
契约检查或 Code Graph 维护。除非用户另行要求，这些不构成当前临时项目的交付门禁。

全局 worktree 绑定和安全底线仍然有效。进入全局超级用户模式后，可以不遵守本文件的
worktree 项目偏好；只有在超级用户模式已按全局协议被用户精确确认后才可这样做，且不能
绕过系统、开发者、安全、数据保护或工具权限规则。

## 2. 最小协同规则

- 只在当前已绑定的 worktree 工作，不切换分支，不把代码写入其他 worktree。
- 使用当前 Task ID 标识任务；不为普通改动额外创建任务、分支或 worktree。
- 只有任务启用了 `planning-with-files` 时才维护 `task_plan.md`、`findings.md` 和
  `progress.md`；不强制维护 Code Graph。
- 保留用户已有改动，不重置、覆盖、清理或整理无关文件。
- 不执行强推、历史重写或其他破坏性 Git 操作，除非用户明确要求且更高优先级规则允许。

## 3. 验证流程

- 每次代码改动只运行改动模块直接相关的 focused 单测。
- 没有现成相关单测时，为非平凡逻辑增加一个最小相关单测；无法合理增加时明确报告未验证
  项，不用全量测试替代。
- 默认不运行全量 `pytest`、全量 `pre-commit`、`uv build`、Code Graph 或完整 E2E。
- 测试失败先修复根因；不要通过静默 fallback、重复 retry、无依据 delay 或兼容分支掩盖失败。
- 文档、规范或纯重命名改动不额外运行无关单测。

## 4. 架构升级规则

- 这是替代实现。允许因架构升级破坏旧模块之间的契约、调用链和联动；不以维持旧行为为默认目标。
- 旧实现只作只读参考。新代码不得同时依赖新旧两套实现，不新增旧名称别名、兼容适配层或
  fallback 来隐藏迁移缺口。
- 确有临时兼容代码必须保留时，必须在代码旁使用不可变的 `# TODO:` 注释，写明保留原因、
  影响范围和删除条件；任何 Agent 不得修改、改写或移动该 TODO 文本。只有达到删除条件并
  整体移除兼容代码时，才可以连同该 TODO 一起删除。
- 修改契约时同步更新当前切片内真实消费者；未迁移的旧消费者不自动获得兼容入口。
- 只完成当前业务切片所需的最小范围，不顺手重构无关模块、清理旧测试或重命名全仓目录。
- 只有当现有模块和公开入口无法满足明确业务需求时，才能新增能力；新增前说明缺口、真实
  调用方、归属模块和最小接口。禁止为未来扩展预留抽象。

## 5. 模块边界

### Python

所有 Python 代码遵守 `docs/features/[规范]python-code-style.md`，包括绝对导入、文件和
函数编排、业务命名、常量归属、注释、docstring、日志和公开入口边界。

### UI Controller

遵守 `docs/features/[规范]ui-code-style.md`：

- `page.py` 是页面包的稳定入口和完整流程编排者；
- `recognition.py` 或语义明确的下层模块只读取和转换页面事实；
- `operations.py` 只放可复用的原子页面操作；
- `workflow.py` 只在存在独立且真实复用的多步骤子流程时创建；
- `constants.py` 只保存模块共享的静态校准数据；
- `__init__.py` 只导出稳定公开入口；
- 不为凑目录创建空文件，不让下层反向依赖 `page.py`，不把内部步骤伪装成公开 API。

### Dispatch Context

遵守 `docs/features/[规范]dispatch-context临时规范.md`：

- 新模块只接收 `autowsgr.dispatch.context` 的 `ContextHandle`；通过 `ctx.runtime` 访问 runtime 服务引用，通过句柄方法读写任务事实；
- runtime composition root 创建并清理设备、配置和 OCR 服务，dispatch 只绑定和暴露引用，不构造或断开服务；
- `ContextTemplate` / `TaskContext` 只保存跨步骤事实，不保存 runtime 服务对象；
- 字段必须有真实调用方、唯一写入者、读取者和生命周期；
- 不动态注册字段，不直接访问 `manager.py`、`state.py` 或内部字典；
- 不向新模块单独传入 `UIContext`、`GameContext` 或 `RuntimeContext`，不创建第二套 Context、进程级任务状态或静默自动重建；
- 新字段与业务切片同步增加，并同步字段表和调用关系。

## 6. Common 调用边界

调用 `autowsgr.common` 的基础能力时，严格使用 `docs/AutoWSGR3.0/common/` 下三份架构文档定义的
稳定公开出口、输入输出、异常和所有权：

- 不引用 common 私有实现路径、内部执行器、私有缓存或深层模块作为新契约；
- `common-system` 负责系统错误、日志、文件和公共基础类型；
- `common-device` 负责设备连接、截图、输入和设备错误；
- `common-vision` 负责 ROI、像素、模板、OpenCV 和 OCR 基础能力；
- 视觉调用统一走 `common.vision` 的公共入口：`screenshot`、`expect_template`/`expect_ocr`/`expect_pixels`
  （`absent=False` 识别存在、`absent=True` 识别不存在）和 `expect_template_center`/`expect_ocr_center`/
  `expect_pixel_center`（返回命中中心）；
  调用方只提供识别数据、识别规则和预期，`ContextHandle` 由 dispatch 统一提供，任何层级都可以调用它；
- 用户配置统一走 `autowsgr.config.UserConfig` 这一棵树；模块配置模型继承
  `common.system.config.ModuleConfig`（不可变、拒绝未声明字段），字段名用 UPPER_SNAKE_CASE，
  与 `usersettings.yaml` 的键一一对应；
- 页面语义、业务状态、路由、任务恢复和模板缓存归各自上层所有者；
- 现有公开能力无法满足明确业务时，只在真实所有者模块增加最小能力，并同步对应架构文档
  和本文件；不得在业务层绕过边界拼接私有实现。

## 7. Ponytail

新增代码遵守 `ponytail`：先问 YAGNI，再复用现有实现，再用标准库、原生能力和已安装依赖，
最后才写最小代码。删除优先于新增，禁止无请求的抽象、包装层、配置、兼容分支和样板代码。
非平凡逻辑留下一个最小可运行的相关单测；已知的刻意简化用 `ponytail:` 注释说明上限和升级条件。

## 8. Coding 记忆

MCP/Engram 记忆只维护 coding 相关内容，不保存非 coding 对话或项目杂事，也不保存密钥、
Token、凭据、隐私日志或未脱敏运行数据。需要保存时只记录：

- 改了什么代码；
- 新增了什么代码及新增理由；
- 减少或删除了什么代码及减少理由；
- 将来需要这些代码时如何按模块、公开入口或测试快速获取；
- 用户提出的 coding 临时需求和约束。

## 9. 规范同步

后续新增或修改代码规范、架构文档、模块公开调用契约时，必须在同一个变更中同步更新本
`AGENTS.md`，保持规则入口与实际文档一致。这里只记录可执行的短规则，详细内容仍以第 1 节
列出的规范和架构文档为准。

## 10. 槽位编号

舰船槽位（slot）是编队的六个物理格，一律从 1 开始编号，范围 1-6：识别结果的键、
函数参数、日志和坐标表都写 1-6，只有确实要取数组下标时才在实现内部临时减一。

旧框架用 0-5，新代码不沿用；新增涉及舰船槽位的代码按本节写。
