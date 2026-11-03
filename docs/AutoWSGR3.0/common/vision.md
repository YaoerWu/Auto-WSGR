# common/vision —— 识别能力

源码目录：`autowsgr/common/vision/`

## 1. 模块定位

**负责**：把"一帧截图"变成可判断的事实——模板匹配、像素签名匹配、OCR 文本识别；对同一目标做有限次重试；把命中结果统一包装成 `RecognitionResult`。

**不负责**：

- 不判断"这是什么页面"（页面语义属于 `application/controller/`）；
- 不点击、不导航、不决定识别失败后业务流程怎么走；
- 不缓存模板，也不管模板文件什么时候更新；
- 不做模糊/语义文本匹配：`expect_ocr` 只做"识别文本与期望文本相等"的比对，模糊规则归调用方。

对外只有 `__init__.py` 与 `service.py` 这一层出口；`adapters/`、`opencv/`、`ocr/`、`numpy/` 都是实现细节。

## 2. 目录与文件

```text
autowsgr/common/vision/
├── __init__.py      导出 ROI / 模板 / 像素 / OCR / 结果模型与七个公开函数
├── service.py       公共入口：screenshot + 六个 expect_*，内含重试与 absent 语义
├── config.py        识别默认值：重试次数与间隔、模板根目录、基准分辨率、置信度、像素容差
├── adapters/
│   ├── template_matching.py  ROI、Template、TemplateMatchResult、load_template、match_template(s)
│   ├── pixel_matching.py     Color、PixelRule、PixelSignature、CompositePixelSignature、match_pixels
│   └── text_recognition.py   RecognitionProfile、TextDetection 产出、prepare/recognize、parse_counter
├── opencv/executor.py       OpenCV 算子：读图、缩放、模板匹配
├── numpy/executor.py        NumPy 算子：图像校验、坐标换算、采样、裁切
└── ocr/executor.py          OCR 引擎封装，单次识别产出 TextDetection 列表
```

## 3. 依赖关系

```text
  controller/checker · navigation/executor · controller/ship_recognition
                    │ expect_template / expect_ocr / expect_pixels / screenshot
                    ▼
            ┌──────────────────┐
            │ service.py       │  重试 · absent · 结果包装
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
            │ adapters/*       │  匹配算法与数据模型
            └──┬─────┬──────┬──┘
               ▼     ▼      ▼
           opencv  numpy   ocr（FastOCR / MaaFramework 模型）
                     │
                     ▼
            common.system.files（模板与截图落盘）· config
```

- **上层谁调它**：`controller/*/checker.py`（判页面、读按钮中心、读数量）、`navigation/executor.py`（探域与到达确认）、`controller/sortie/battle_preparation/ship_recognition/`（六槽位 OCR）。
- **它下层依赖谁**：OpenCV、NumPy、OCR 引擎、`common.system.files`（`load_image` / `save_image`）。取帧经 `ctx.runtime.ctrl.screenshot()`，不直接依赖 `DeviceService`。

## 4. 调用入口与出口

### 4.1 结果模型

```python
@dataclass(frozen=True, slots=True)
class RecognitionResult(Generic[T]):
    satisfied: bool
    observation: T
    screenshot: numpy.ndarray
```

`satisfied` 是"本次判断是否符合预期"，`observation` 是原始事实（模板命中列表 / 文本检测列表 / 像素命中列表），`screenshot` 是本次判定用的那一帧。`absent` 只改变 `satisfied` 的含义，不改变 `observation`：`absent=True` 时"没识别到"才算满足。

### 4.2 截图

```python
def screenshot(ctx: ContextHandle) -> numpy.ndarray
```

取一帧 RGB，同时通过 `ctx.record_screenshot(frame)` 把这一帧记进任务上下文，供后续复用与排查。**一次 expect 调用只截一帧**，命中多个目标时共享同一帧。

### 4.3 模板

```python
def expect_template(
    ctx: ContextHandle, *, template: Template, roi: ROI | None = None,
    confidence: float = OPENCV_TEMPLATE_CONFIDENCE, min_matches: int = 1,
    attempts: int = DEFAULT_RECOGNITION_ATTEMPTS,
    interval_seconds: float = DEFAULT_RECOGNITION_INTERVAL_SECONDS,
    absent: bool = False,
) -> RecognitionResult[list[TemplateMatchResult]]

def expect_template_center(
    ctx: ContextHandle, *, template: Template, roi: ROI | None = None,
    confidence: float = OPENCV_TEMPLATE_CONFIDENCE,
    attempts: int = DEFAULT_RECOGNITION_ATTEMPTS,
    interval_seconds: float = DEFAULT_RECOGNITION_INTERVAL_SECONDS,
) -> tuple[float, float] | None
```

`TemplateMatchResult` 含 `matched / score / location / template_path / roi / center`；`center` 是**归一化**坐标（0–1），可直接交给 `page.py` 点击。

### 4.4 像素

```python
def expect_pixels(
    ctx: ContextHandle, *, signature: PixelSignature | CompositePixelSignature,
    roi: ROI | None = None, with_details: bool = False, min_matches: int = 1,
    attempts: int = DEFAULT_RECOGNITION_ATTEMPTS,
    interval_seconds: float = DEFAULT_RECOGNITION_INTERVAL_SECONDS,
    absent: bool = False,
) -> RecognitionResult[list[PixelMatchResult]]

def expect_pixel_center(...) -> tuple[float, float] | None
```

用于没有模板资源的纯色/多色块判断（血条、按钮可用态）。`Color` 支持色差比较，`CompositePixelSignature` 组合多个签名。

### 4.5 OCR

```python
def expect_ocr(
    ctx: ContextHandle, *, expect: str | Sequence[str] | None = None,
    roi: ROI | Sequence[ROI] | None = None, allowlist: str = '',
    recognition_profile: str = 'full', candidates: Sequence[str] | None = None,
    attempts: int = DEFAULT_RECOGNITION_ATTEMPTS,
    interval_seconds: float = DEFAULT_RECOGNITION_INTERVAL_SECONDS,
    absent: bool = False,
) -> RecognitionResult[list[TextDetection] | list[list[TextDetection]]]

def expect_ocr_center(...) -> tuple[float, float] | None
```

- `roi` 传序列时，同一帧内按区域逐个识别，`observation` 变成"按 ROI 分组的列表"，顺序与 `roi` 一致（演习六槽位识别即用此形态）。
- `expect` 是精确文本比对；需要"包含/正则/模糊"时由调用方拿 `observation` 自己判。
- `allowlist` 限制字符集，`recognition_profile` 选择预处理档位，`candidates` 给候选词表。

### 4.6 重试与参数校验

六个 `expect_*` 共用私有 `_retry(ctx, *, task, observe, accept, attempts, interval_seconds)`：每轮先 `screenshot`，再 `observe`，再 `accept`，满足即返回，最后一轮仍不满足则返回 `satisfied=False`。

`attempts < 1` 抛 `ValueError('attempts 必须是大于零的整数')`；`interval_seconds < 0` 抛 `ValueError`。

## 5. 怎么维护

- **模板放对目录**：模板根是 `OPENCV_TEMPLATE_ROOT = <仓库>/resources/image`，`load_template` 只接受该根下的相对路径；绝对路径或含 `..` 抛 `ValueError('模板路径必须是 OPENCV_TEMPLATE_ROOT 下的相对路径')`。控制器用 `controller/template.py` 拼 `application/<namespace>/<文件名>`。
- **基准分辨率是 1280x720**：`ROI` 用归一化坐标（`__post_init__` 强制 `0 <= x1 < x2 <= 1`、`0 <= y1 < y2 <= 1`）；模板分辨率与截图不同时按比例缩放，不要自己预先改图。
- **新增识别能力的位置**：先在 `adapters/*` 写算法与数据模型，再在 `service.py` 加带重试的公开函数，最后在 `__init__.py` 导出。不要在上层直接调 `opencv/executor.py`。
- **不要在这里写页面规则**：ROI 数值属于具体页面，写进对应 `controller/<页面>/checker.py`；`common/vision` 只保留识别通用默认值。
- **一次判断只用一帧**：多个目标的识别放进同一个 `expect_*` 调用（例如 `read_home_layer` 用七个模板比一帧），不要在页面代码里连截多帧，既慢又会出现层间撕裂。
- **模糊匹配归调用方**：`expect_ocr` 的 `expect` 是相等比对，别在这里加"包含"分支，否则各页面口径会漂移。

## 6. 索引

- [返回总览](../README.md)
- [common/system.md](system.md) —— 模板/截图文件的受限读写
- [common/device.md](device.md) —— `ctx.runtime.ctrl.screenshot()` 的提供方
- [application/controller.md](../application/controller/README.md) —— 模板与 ROI 的主要消费方
- [application/navigation.md](../application/navigation/README.md) —— 用 `expect_*` 做域探针与到达确认
