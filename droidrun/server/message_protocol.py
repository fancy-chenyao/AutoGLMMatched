"""
消息协议定义 - 定义 WebSocket 通信的消息格式和类型
"""
import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum


class MessageType(Enum):
    """消息类型枚举"""
    # 连接相关
    SERVER_READY = "server_ready"
    
    # 心跳相关
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"
    
    # 命令相关
    COMMAND = "command"
    COMMAND_RESPONSE = "command_response"
    
    # 错误相关
    ERROR = "error"
    
    # 任务相关
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    TASK_STATUS = "task_status"
    
    # 用户交互相关
    USER_QUESTION = "user_question"
    USER_ANSWER = "user_answer"


class MessageProtocol:
    """消息协议工具类"""
    
    # 协议版本
    PROTOCOL_VERSION = "1.0"
    
    @staticmethod
    def create_message(
        message_type: MessageType,
        data: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        error: Optional[str] = None,
        device_id: Optional[str] = None,
        status: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建标准消息
        """
        message = {
            "type": message_type.value if isinstance(message_type, MessageType) else message_type,
        }
        
        # 只有特定的消息类型包含 version 和 timestamp
        if message_type in [MessageType.HEARTBEAT, MessageType.TASK_REQUEST]:
            message["version"] = MessageProtocol.PROTOCOL_VERSION
            message["timestamp"] = int(time.time())
        
        # 添加请求ID
        if request_id:
            message["request_id"] = request_id
        
        # 添加设备ID
        if device_id:
            message["device_id"] = device_id
        
        # 添加状态
        if status:
            message["status"] = status
        elif error:
            message["status"] = "error"
        elif message_type in [MessageType.HEARTBEAT, MessageType.TASK_REQUEST, MessageType.SERVER_READY]:
            message["status"] = "success"
        
        # 添加数据或错误
        if error:
            message["error"] = error
        
        if data is not None:
            message["data"] = data
        
        # 添加其他字段
        message.update(kwargs)
        
        return message
    
    @staticmethod
    def create_server_ready(status: str = "success") -> Dict[str, Any]:
        """创建 server_ready 消息"""
        return MessageProtocol.create_message(
            MessageType.SERVER_READY,
            status=status
        )
    
    @staticmethod
    def create_command_message(
        command: str,
        params: Dict[str, Any],
        request_id: str,
    ) -> Dict[str, Any]:
        """创建命令消息"""
        return MessageProtocol.create_message(
            MessageType.COMMAND,
            data={
                "command": command,
                "params": params
            },
            request_id=request_id
        )
    
    @staticmethod
    def create_command_response(
        request_id: str,
        status: str = "success",
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建命令响应消息"""
        return MessageProtocol.create_message(
            MessageType.COMMAND_RESPONSE,
            request_id=request_id,
            status=status,
            data=data,
            error=error,
            device_id=device_id
        )
    
    @staticmethod
    def create_heartbeat_message(device_id: str) -> Dict[str, Any]:
        """创建心跳消息"""
        return MessageProtocol.create_message(
            MessageType.HEARTBEAT,
            device_id=device_id
        )
    
    @staticmethod
    def create_heartbeat_ack() -> Dict[str, Any]:
        """创建心跳确认消息"""
        return MessageProtocol.create_message(
            MessageType.HEARTBEAT_ACK,
            status="success"
        )
    
    @staticmethod
    def create_error_message(
        error: str,
        request_id: Optional[str] = None,
        device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建错误消息"""
        return MessageProtocol.create_message(
            MessageType.ERROR,
            error=error,
            request_id=request_id,
            device_id=device_id,
            status="error"
        )
    
    @staticmethod
    def validate_message(message: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """验证消息格式"""
        if "type" not in message:
            return False, "Missing 'type' field"
        
        m_type = message.get("type")
        
        # 命令消息验证
        if m_type == MessageType.COMMAND.value:
            if "request_id" not in message:
                return False, "Command message missing 'request_id'"
            data = message.get("data")
            if not isinstance(data, dict) or "command" not in data:
                return False, "Command message missing 'command' in data"
        
        # 任务请求验证
        if m_type == MessageType.TASK_REQUEST.value:
            data = message.get("data")
            if not isinstance(data, dict) or "goal" not in data:
                return False, "Task request missing 'goal' in data"
        
        return True, None
    
    @staticmethod
    def parse_message(message_str: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        """解析消息字符串"""
        try:
            message = json.loads(message_str)
            if not isinstance(message, dict):
                return None, "Message is not a dictionary"
            is_valid, error = MessageProtocol.validate_message(message)
            if not is_valid:
                return None, error
            return message, None
        except Exception as e:
            return None, f"Parse error: {str(e)}"
     
    @staticmethod
    def create_task_request(
        goal: str,
        request_id: str,
        device_id: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """创建任务请求消息"""
        data = {"goal": goal}
        if options:
            data["options"] = options
        
        return MessageProtocol.create_message(
            MessageType.TASK_REQUEST,
            data=data,
            request_id=request_id,
            device_id=device_id
        )
    
    @staticmethod
    def create_task_response(
        request_id: str,
        status: str = "success",
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建任务响应消息"""
        kwargs = {}
        if status == "error":
            kwargs["error"] = error
        elif result is not None:
            kwargs["result"] = result
            
        return MessageProtocol.create_message(
            MessageType.TASK_RESPONSE,
            request_id=request_id,
            status=status,
            **kwargs
        )
    
    @staticmethod
    def create_task_status(
        request_id: str,
        status: str,
        progress: Optional[float] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建任务状态更新消息"""
        data = {"status": status}
        if progress is not None:
            data["progress"] = progress
        if message:
            data["message"] = message
        
        return MessageProtocol.create_message(
            MessageType.TASK_STATUS,
            data=data,
            request_id=request_id
        )

    @staticmethod
    def create_user_question(
        question_id: str,
        question_text: str,
        question_type: str = "text",
        options: Optional[List[Any]] = None,
        default_value: Optional[Any] = None,
        timeout_seconds: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        创建用户问题消息
        
        Args:
            question_id: 问题唯一标识
            question_text: 问题文本
            question_type: 问题类型 (text, choice, confirm)
            options: 选项列表
            default_value: 默认值
            timeout_seconds: 超时时间
        """
        data = {
            "question_id": question_id,
            "question_text": question_text,
            "question_type": question_type
        }
        if options is not None:
            data["options"] = options
        if default_value is not None:
            data["default_value"] = default_value
        if timeout_seconds is not None:
            data["timeout_seconds"] = timeout_seconds
        
        return MessageProtocol.create_message(
            MessageType.USER_QUESTION,
            data=data
        )
    
    @staticmethod
    def create_user_answer(
        question_id: str,
        answer: str,
    ) -> Dict[str, Any]:
        """创建用户回答消息"""
        data = {
            "question_id": question_id,
            "answer": answer
        }
        return MessageProtocol.create_message(
            MessageType.USER_ANSWER,
            data=data
        )

