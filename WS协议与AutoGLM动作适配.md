# WebSocket相关

## heartbeat 心跳（发送）
- 字典：{
  "type": "heartbeat",
  "version": "1.0",
  "timestamp": "ISO-8601",
  "device_id": "xxxx-device-id",
  "status": "success"
}
- 参数：device_id

## heartbeat_ack 心跳确认（接收）
- 示例：{
  "type": "heartbeat_ack",
  "status": "success"
}

## task_request 任务请求（发送）
- 字典：{
  "type": "task_request",
  "request_id": "xxxx-uuid",
  "device_id": "xxxx-device-id",
  "status": "success",
  "data": { "goal": "自然语言任务目标", "options": { ... } }
}
- 参数：goal（必填）、options（可选）

## task_status 任务状态（接收）
- 示例：{
  "type": "task_status",
  "data": { "status": "running", "progress": 0.5, "message": "处理中" }
}

## task_response 任务响应（接收）
- 成功：{
  "type": "task_response",
  "status": "success",
  "result": { ... }
}
- 失败：{
  "type": "task_response",
  "status": "error",
  "error": "原因信息"
}

## command 命令（接收顶层结构）
- 字典：{
  "type": "command",
  "request_id": "xxxx-uuid",
  "data": { "command": "tap", "params": { ... } }
}
- 说明：各具体动作的 params 见下方“动作空间”

## command_response 命令响应（发送）
- accepted：{
  "type": "command_response",
  "request_id": "xxxx-uuid",
  "device_id": "xxxx-device-id",
  "status": "accepted"
}
- success：{
  "type": "command_response",
  "request_id": "xxxx-uuid",
  "device_id": "xxxx-device-id",
  "status": "success",
  "data": { ... }
}
- error：{
  "type": "command_response",
  "request_id": "xxxx-uuid",
  "device_id": "xxxx-device-id",
  "status": "error",
  "error": "错误信息"
}

## error 错误消息（发送/接收）
- 字典：{
  "type": "error",
  "status": "error",
  "error": "错误信息",
  "request_id": "xxxx-uuid（可选）",
  "device_id": "xxxx-device-id（可选）"
}

## user_question 用户问题（接收）
- 示例：{
  "type": "user_question",
  "question_id": "xxxx-id",
  "default_value": "默认值"
}

## user_answer 用户回答（发送）
- 字典：{
  "type": "user_answer",
  "question_id": "xxxx-id",
  "answer": "答案内容"
}

## server_ready 服务器就绪（接收）
- 示例：{
  "type": "server_ready",
  "status": "success"
}

# 动作空间
## take_screenshot 截图
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "take_screenshot",
    "params": {}
  }
}
- 参数：无

## get_state 获取状态
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "get_state",
    "params": { "stabilize_timeout_ms": 5000, "stable_window_ms": 500, "include_screenshot": false }
  }
}
- 参数：stabilize_timeout_ms（可选）、stable_window_ms（可选）、include_screenshot（可选）

## tap 点击
- 字典：{
    "type": "COMMAND",
    "request_id": "xxxx-uuid",
    "data": {
        "command": "tap",
        "params": { "element":[x,y] or "index": x }
    }
  }
- 参数：element、index（可选）

## swipe 滑动
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "swipe",
    "params": { "start":[x1,y1], "end":[x2,y2], "duration_ms": 300 }
  }
}
- 参数：start、end

## input_text 输入
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "input_text",
    "params": { "text": "xxx", "element":[x,y] or "index": x }
  }
}
- 参数：element、index（可选）、text；

## back 返回上一页
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "back",
    "params": {}
  }
}
- 参数：无

## home 返回主页
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "home",
    "params": {}
  }
}
- 参数：无

## double tap 双击
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "double tap",
    "params": { "element":[x,y] or "index": x }
  }
}
- 参数：element、index（可选）

## long press 长按
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "long press",
    "params": { "element":[x,y] or "index": x }
  }
}
- 参数：element、index（可选）

## wait 等待
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "wait",
    "params": { "duration": "x seconds" }
  }
}
- 参数：duration

## take_over 接管
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "take_over",
    "params": { "message": "xxx" }
  }
}
- 参数：message

## note 备注（AutoGLM仅占位实现，并未执行实际业务逻辑）
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "note",
    "params": { "message": "True" }
  }
}
- 参数：message

## call_api 调用API（AutoGLM仅占位实现，并未执行实际业务逻辑）
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "call_api",
    "params": { "instruction": "xxx" }
  }
}
- 参数：instruction

## interact 交互（AutoGLM仅占位实现，并未执行实际业务逻辑）
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "interact",
    "params": {}
  }
}
- 参数：无

## finish 结束
- 字典：{
  "type": "COMMAND",
  "request_id": "xxxx-uuid",
  "data": {
    "command": "finish",
    "params": {}
  }
}
- 参数：message
