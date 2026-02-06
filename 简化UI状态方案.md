# 简化UI状态方案

## 问题背景

当前UI状态传给LLM的Token数量过大：
- 日期选择器：100+元素 × 150 tokens/元素 = **15,000-20,000 tokens**
- 每轮LLM推理耗时：5-8秒
- 微冷启动需要2-3轮，总计：15-24秒

## 目标

将UI状态Token数量从 **15,000-20,000** 降低到 **3,000-5,000**，预期效果：
- 每轮LLM推理耗时：5-8秒 → **2-3秒**
- 微冷启动总耗时：15-24秒 → **6-9秒**

---

## 方案1：过滤非关键元素（推荐）⭐⭐⭐⭐⭐

### 原理

只保留与任务相关的元素，过滤掉无关元素。

### 过滤规则

| 规则 | 说明 | 预期过滤比例 |
|------|------|-------------|
| 只保留clickable元素 | 非clickable元素无法交互 | 过滤50-60% |
| 过滤空text元素 | 无文本的元素通常不重要 | 过滤20-30% |
| 过滤系统UI元素 | 状态栏、导航栏等 | 过滤10-15% |
| 深度限制 | 只保留前3层嵌套 | 过滤10-20% |

### 实现方式

**修改文件**：`droidrun/agent/utils/chat_utils.py`

**修改函数**：`_format_ui_elements`

```python
def _format_ui_elements(ui_data, level=0, config=None) -> str:
    """Format UI elements with optional filtering"""
    if not ui_data:
        return ""
    
    # 默认配置
    config = config or {}
    max_depth = config.get('max_depth', 10)  # 最大嵌套深度
    only_clickable = config.get('only_clickable', False)  # 只保留clickable
    filter_empty_text = config.get('filter_empty_text', False)  # 过滤空text
    max_elements = config.get('max_elements', 1000)  # 最大元素数量
    
    # 深度限制
    if level > max_depth:
        return ""
    
    formatted_lines = []
    element_count = [0]  # 使用列表以便在递归中修改
    
    elements = ui_data if isinstance(ui_data, list) else [ui_data]
    
    for element in elements:
        if element_count[0] >= max_elements:
            break
            
        if not isinstance(element, dict):
            continue
        
        # 过滤规则
        clickable = element.get('clickable', False)
        text = element.get('text', '')
        
        if only_clickable and not clickable:
            continue
        if filter_empty_text and not text:
            continue
        
        # 格式化元素（简化版）
        # ... 原有格式化逻辑
        element_count[0] += 1
    
    return "\n".join(formatted_lines)
```

**添加配置**：`droidrun/config/unified_config.py`

```python
@dataclass
class UIStateConfig:
    """UI状态配置"""
    max_depth: int = 10  # 最大嵌套深度
    only_clickable: bool = False  # 只保留clickable元素
    filter_empty_text: bool = False  # 过滤空text元素
    max_elements: int = 1000  # 最大元素数量
    simplified_format: bool = False  # 使用简化格式
```

**配置示例**：

```yaml
# droidrun.yaml
ui_state:
  max_depth: 3  # 只保留前3层
  only_clickable: true  # 只保留clickable元素
  filter_empty_text: true  # 过滤空text元素
  max_elements: 50  # 最多50个元素
```

### 预期效果

| 场景 | 原始元素数 | 过滤后元素数 | Token减少 |
|------|-----------|-------------|----------|
| 日期选择器 | 100+ | 30-40 | 60-70% |
| 普通页面 | 50-80 | 20-30 | 50-60% |
| 列表页面 | 200+ | 50-80 | 60-75% |

---

## 方案2：简化元素格式（推荐）⭐⭐⭐⭐

### 原理

减少每个元素的输出字段，只保留关键信息。

### 当前格式（~150 tokens/元素）

```
12. android.widget.TextView: "com.example:id/date_text", "28", clickable=true - (100,200,150,250)
```

### 简化格式（~50 tokens/元素）

```
12. "28" [clickable]
```

### 实现方式

**修改函数**：`_format_ui_elements`

```python
def _format_ui_elements_simplified(ui_data, level=0) -> str:
    """简化格式：只输出 index, text, clickable"""
    if not ui_data:
        return ""
    
    formatted_lines = []
    elements = ui_data if isinstance(ui_data, list) else [ui_data]
    
    for element in elements:
        if not isinstance(element, dict):
            continue
        
        index = element.get('index', '')
        text = element.get('text', '')
        clickable = element.get('clickable', False)
        
        # 简化格式
        if text:
            line = f"{index}. \"{text}\""
        else:
            class_name = element.get('className', '').split('.')[-1]  # 只取类名最后一部分
            line = f"{index}. [{class_name}]"
        
        if clickable:
            line += " [clickable]"
        
        formatted_lines.append(line)
    
    return "\n".join(formatted_lines)
```

### 预期效果

| 指标 | 原始格式 | 简化格式 | 减少比例 |
|------|---------|---------|---------|
| 每元素Token | ~150 | ~50 | 67% |
| 100元素总Token | 15,000 | 5,000 | 67% |

---

## 方案3：智能过滤（高级）⭐⭐⭐⭐⭐

### 原理

根据微冷启动的子目标，智能过滤只保留相关元素。

### 示例

**子目标**："选择2025年12月28日"

**智能过滤**：
- 只保留包含"28"、"12"、"2025"、"确认"、"取消"等关键词的元素
- 只保留日期选择器相关的className（如DatePicker、Calendar等）

### 实现方式

**新增函数**：`filter_ui_by_goal`

```python
def filter_ui_by_goal(ui_data: List[Dict], goal: str) -> List[Dict]:
    """根据目标智能过滤UI元素"""
    import re
    
    # 从目标中提取关键词
    keywords = extract_keywords(goal)  # 如 ["28", "12", "2025", "确认"]
    
    filtered = []
    for element in flatten_ui(ui_data):
        text = element.get('text', '')
        resource_id = element.get('resourceId', '')
        
        # 检查是否包含关键词
        if any(kw in text or kw in resource_id for kw in keywords):
            filtered.append(element)
        # 保留所有clickable元素（可能是确认/取消按钮）
        elif element.get('clickable', False):
            filtered.append(element)
    
    return filtered

def extract_keywords(goal: str) -> List[str]:
    """从目标中提取关键词"""
    import re
    
    keywords = []
    
    # 提取日期
    date_patterns = [
        r'(\d{4})年',  # 年份
        r'(\d{1,2})月',  # 月份
        r'(\d{1,2})[日号]',  # 日期
    ]
    for pattern in date_patterns:
        matches = re.findall(pattern, goal)
        keywords.extend(matches)
    
    # 提取常见操作词
    action_words = ['确认', '取消', '提交', '保存', '选择', '完成']
    keywords.extend([w for w in action_words if w in goal])
    
    return list(set(keywords))
```

### 预期效果

| 场景 | 原始元素数 | 智能过滤后 | Token减少 |
|------|-----------|-----------|----------|
| 选择日期 | 100+ | 10-15 | 85-90% |
| 输入文本 | 50+ | 5-10 | 80-90% |
| 点击按钮 | 30+ | 3-5 | 85-90% |

---

## 方案4：分层传输（高级）⭐⭐⭐

### 原理

先传输简化版UI，如果LLM无法完成任务，再传输完整版。

### 实现方式

```python
async def get_ui_state_progressive(tools, goal: str) -> str:
    """渐进式获取UI状态"""
    
    # 第1层：只传输clickable元素的简化格式
    ui_state = await tools.get_state_async()
    simplified = format_ui_simplified(ui_state, only_clickable=True)
    
    # 如果元素数量少于阈值，直接返回
    if count_elements(simplified) < 20:
        return simplified
    
    # 第2层：智能过滤
    filtered = filter_ui_by_goal(ui_state, goal)
    return format_ui_simplified(filtered)
```

---

## 综合方案（推荐）

### 配置设计

```yaml
# droidrun.yaml
ui_state:
  # 基础过滤
  max_depth: 5  # 最大嵌套深度
  max_elements: 100  # 最大元素数量
  only_clickable: false  # 普通模式保留所有元素
  filter_empty_text: false  # 普通模式保留空text
  
  # 简化格式
  simplified_format: false  # 普通模式使用完整格式
  include_bounds: true  # 包含bounds信息
  include_resource_id: true  # 包含resourceId
  include_class_name: true  # 包含className
  
  # 微冷启动专用配置
  micro_cold_start:
    max_depth: 3  # 微冷启动只保留前3层
    max_elements: 50  # 微冷启动最多50个元素
    only_clickable: true  # 微冷启动只保留clickable
    filter_empty_text: true  # 微冷启动过滤空text
    simplified_format: true  # 微冷启动使用简化格式
    smart_filter: true  # 微冷启动启用智能过滤
```

### 代码修改清单

| 文件 | 修改内容 |
|------|---------|
| `droidrun/config/unified_config.py` | 添加 `UIStateConfig` 配置类 |
| `droidrun/agent/utils/chat_utils.py` | 修改 `_format_ui_elements` 支持配置 |
| `droidrun/agent/utils/chat_utils.py` | 新增 `filter_ui_by_goal` 智能过滤函数 |
| `droidrun/agent/codeact/codeact_agent_micro.py` | 使用微冷启动专用配置 |

### 预期效果

| 场景 | 当前Token | 优化后Token | 减少比例 | LLM耗时 |
|------|----------|------------|---------|--------|
| 日期选择器 | 15,000-20,000 | 2,000-3,000 | 85% | 5-8秒 → 2-3秒 |
| 普通页面 | 8,000-12,000 | 2,000-4,000 | 70% | 3-5秒 → 1-2秒 |
| 列表页面 | 20,000-30,000 | 3,000-5,000 | 85% | 8-12秒 → 2-4秒 |

### 微冷启动总耗时预期

| 指标 | 当前 | 优化后 | 改善 |
|------|------|--------|------|
| 单轮LLM耗时 | 5-8秒 | 2-3秒 | 60% |
| 微冷启动轮次 | 2-3轮 | 2-3轮 | 不变 |
| 单个子任务耗时 | 15-24秒 | 6-9秒 | 60% |
| 2个子任务总耗时 | 30-48秒 | 12-18秒 | 60% |

---

## 实施建议

### 第一阶段：基础过滤（低风险，高收益）

1. 添加 `only_clickable` 配置，过滤非clickable元素
2. 添加 `max_elements` 配置，限制最大元素数量
3. 添加 `max_depth` 配置，限制嵌套深度

**预期收益**：Token减少50-60%，LLM耗时减少40-50%

### 第二阶段：简化格式（低风险，中收益）

1. 添加 `simplified_format` 配置
2. 实现简化格式输出（只保留index、text、clickable）

**预期收益**：Token再减少30-40%，LLM耗时再减少20-30%

### 第三阶段：智能过滤（中风险，高收益）

1. 实现 `filter_ui_by_goal` 智能过滤
2. 根据子目标提取关键词，只保留相关元素

**预期收益**：Token减少80-90%，LLM耗时减少60-70%

---

## 风险评估

| 方案 | 风险等级 | 风险说明 | 缓解措施 |
|------|---------|---------|---------|
| 基础过滤 | 低 | 可能过滤掉需要的元素 | 保留所有clickable元素 |
| 简化格式 | 低 | LLM可能需要更多信息 | 保留关键字段 |
| 智能过滤 | 中 | 关键词提取可能不准确 | 保留所有clickable元素作为兜底 |

---

## 总结

通过简化UI状态，可以将微冷启动的LLM耗时从 **5-8秒/轮** 降低到 **2-3秒/轮**，单个子任务耗时从 **15-24秒** 降低到 **6-9秒**，整体热启动+微冷启动耗时从 **80秒** 降低到 **50-60秒**。
