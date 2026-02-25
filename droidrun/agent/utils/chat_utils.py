import base64
import re
import inspect


import json
import logging
from typing import List, TYPE_CHECKING, Optional, Tuple
from droidrun.agent.context import Reflection
from llama_index.core.base.llms.types import ChatMessage, ImageBlock, TextBlock

if TYPE_CHECKING:
    from droidrun.tools import Tools

logger = logging.getLogger("droidrun")

def message_copy(message: ChatMessage, deep = True) -> ChatMessage:
    if deep:
        copied_message = message.model_copy()
        copied_message.blocks = [block.model_copy () for block in message.blocks]

        return copied_message
    copied_message = message.model_copy()

    # Create a new, independent list containing the same block references
    copied_message.blocks = list(message.blocks) # or original_message.blocks[:]

    return copied_message

async def add_reflection_summary(reflection: Reflection, chat_history: List[ChatMessage]) -> List[ChatMessage]:
    """Add reflection summary and advice to help the planner understand what went wrong and what to do differently."""
    
    reflection_text = "\n### The last task failed. You have additional information about what happenend. \nThe Reflection from Previous Attempt:\n"
    
    if reflection.summary:
        reflection_text += f"**What happened:** {reflection.summary}\n\n"
    
    if reflection.advice:
        reflection_text += f"**Recommended approach for this retry:** {reflection.advice}\n"
    
    reflection_block = TextBlock(text=reflection_text)
    
    # Copy chat_history and append reflection block to the last message
    chat_history = chat_history.copy()
    chat_history[-1] = message_copy(chat_history[-1])
    chat_history[-1].blocks.append(reflection_block)
    
    return chat_history

def _format_ui_elements(ui_data, level=0, hide_index=False) -> str:
    """Format UI elements in natural language: index. className: resourceId, text - bounds"""
    if not ui_data:
        return ""
    
    formatted_lines = []
    indent = "  " * level  # Indentation for nested elements
    
    # Handle both list and single element
    elements = ui_data if isinstance(ui_data, list) else [ui_data]
    
    for element in elements:
        if not isinstance(element, dict):
            continue
            
        # Extract element properties
        index = element.get('index', '')
        class_name = element.get('className', '')
        resource_id = element.get('resourceId', '')
        text = element.get('text', '')
        bounds = element.get('bounds', '')
        clickable = element.get('clickable', False)
        children = element.get('children', [])
        
        
        # Format the line: index. className: resourceId, text, parentIndex, clickable - bounds
        line_parts = []
        if not hide_index and index != '':
            line_parts.append(f"{index}.")
        if class_name:
            line_parts.append(class_name + ":")
        
        details = []
        if resource_id:
            details.append(f'"{resource_id}"')
        if text:
            details.append(f'"{text}"')
        details.append(f"clickable={clickable}")
        
        if details:
            line_parts.append(", ".join(details))
        
        if bounds:
            line_parts.append(f"- ({bounds})")
        
        formatted_line = f"{indent}{' '.join(line_parts)}"
        formatted_lines.append(formatted_line)
        
        # Recursively format children with increased indentation
        if children:
            child_formatted = _format_ui_elements(children, level + 1, hide_index=hide_index)
            if child_formatted:
                formatted_lines.append(child_formatted)
    
    return "\n".join(formatted_lines)

async def add_ui_text_block(ui_state: str, chat_history: List[ChatMessage], persona_name: str = "", copy = True) -> List[ChatMessage]:
    """Add UI elements to the chat history without modifying the original."""
    if ui_state:
        # If using AutoGLM-Phone persona, we might want to skip or simplify UI tree
        # based on Open-AutoGLM's behavior (which is purely vision-based).
        # However, keeping it doesn't hurt as long as the prompt is clear.
        # For now, let's keep it but make it optional or formatted differently if needed.
        
        try:
            ui_data = json.loads(ui_state) if isinstance(ui_state, str) else ui_state
            
            # If AutoGLM-Phone, use a more concise header and hide index
            if persona_name == "AutoGLM-Phone":
                formatted_ui = _format_ui_elements(ui_data, hide_index=True)
                text = f"** UI Elements **\n\n{formatted_ui}"
            else:
                formatted_ui = _format_ui_elements(ui_data, hide_index=False)
                text = f"""
Current UI elements from the device in the schema 'index. className: resourceId, text, clickable=true/false - bounds(x1,y1,x2,y2)':

Important Notes:
- Use tap_by_index(index) to interact with elements
- Only elements with clickable=true can be directly tapped

Elements:
{formatted_ui}
"""
            ui_block = TextBlock(text=text)
        except (json.JSONDecodeError, TypeError):
            ui_block = TextBlock(text="\nCurrent Clickable UI elements from the device using the custom TopViewService:\n```json\n" + json.dumps(ui_state) + "\n```\n")
        
        if copy:
            chat_history = chat_history.copy()
            chat_history[-1] = message_copy(chat_history[-1])
        chat_history[-1].blocks.append(ui_block)
    return chat_history

async def add_screenshot_image_block(screenshot, chat_history: List[ChatMessage], copy = True) -> List[ChatMessage]:
    if screenshot:
        image_block = ImageBlock(image=screenshot)
        if copy:
            chat_history = chat_history.copy()  # Create a copy of chat history to avoid modifying the original
            chat_history[-1] = message_copy(chat_history[-1])
        chat_history[-1].blocks.append(image_block)
    return chat_history


async def add_phone_state_block(phone_state, chat_history: List[ChatMessage], persona_name: str = "") -> List[ChatMessage]:
    
    # Format the phone state data nicely
    if isinstance(phone_state, dict) and 'error' not in phone_state:
        current_app = phone_state.get('currentApp', '')
        package_name = phone_state.get('packageName', 'Unknown')
        keyboard_visible = phone_state.get('keyboardVisible', False)
        focused_element = phone_state.get('focusedElement')
        
        # If AutoGLM-Phone persona, match Open-AutoGLM's Screen Info format: {"current_app": "..."}
        if persona_name == "AutoGLM-Phone":
            screen_info = {"current_app": current_app}
            # Open-AutoGLM uses "** Screen Info **\n\nJSON"
            phone_state_text = f"** Screen Info **\n\n{json.dumps(screen_info, ensure_ascii=False)}"
        else:
            # Format the focused element
            if focused_element:
                element_text = focused_element.get('text', '')
                element_class = focused_element.get('className', '')
                element_resource_id = focused_element.get('resourceId', '')
                
                # Build focused element description
                focused_desc = f"'{element_text}' {element_class}"
                if element_resource_id:
                    focused_desc += f" | ID: {element_resource_id}"
            else:
                focused_desc = "None"
            
            phone_state_text = f"""
**Current Phone State:**
• **App:** {current_app} ({package_name})
• **Keyboard:** {'Visible' if keyboard_visible else 'Hidden'}
• **Focused Element:** {focused_desc}
        """
    else:
        # Handle error cases or malformed data
        if isinstance(phone_state, dict) and 'error' in phone_state:
            phone_state_text = f"\n📱 **Phone State Error:** {phone_state.get('message', 'Unknown error')}\n"
        else:
            phone_state_text = f"\n📱 **Phone State:** {phone_state}\n"
    
    ui_block = TextBlock(text=phone_state_text)
    chat_history = chat_history.copy()
    chat_history[-1] = message_copy(chat_history[-1])
    chat_history[-1].blocks.append(ui_block)
    return chat_history

async def add_packages_block(packages, chat_history: List[ChatMessage]) -> List[ChatMessage]:
    
    ui_block = TextBlock(text=f"\nInstalled packages: {packages}\n```\n")
    chat_history = chat_history.copy()
    chat_history[-1] = message_copy(chat_history[-1])
    chat_history[-1].blocks.append(ui_block)
    return chat_history

async def add_memory_block(memory: List[str], chat_history: List[ChatMessage]) -> List[ChatMessage]:
    memory_block = "\n### Remembered Information:\n"
    for idx, item in enumerate(memory, 1):
        memory_block += f"{idx}. {item}\n"
    
    for i, msg in enumerate(chat_history):
        if msg.role == "user":
            if isinstance(msg.content, str):
                updated_content = f"{memory_block}\n\n{msg.content}"
                chat_history[i] = ChatMessage(role="user", content=updated_content)
            elif isinstance(msg.content, list):
                memory_text_block = TextBlock(text=memory_block)
                content_blocks = [memory_text_block] + msg.content
                chat_history[i] = ChatMessage(role="user", content=content_blocks)
            break
    return chat_history

async def get_reflection_block(reflections: List[Reflection]) -> ChatMessage:
    reflection_block = "\n### You also have additional Knowledge to help you guide your current task from previous expierences:\n"
    for reflection in reflections:
        reflection_block += f"**{reflection.advice}\n"
    
    return ChatMessage(role="user", content=reflection_block)
        
async def add_task_history_block(all_tasks: list[dict], chat_history: List[ChatMessage]) -> List[ChatMessage]:
    """Experimental task history with all previous tasks."""
    if not all_tasks:
        return chat_history

    lines = ["### Task Execution History (chronological):"]
    for index, task in enumerate(all_tasks, 1):
        description: str
        status_value: str

        if hasattr(task, "description") and hasattr(task, "status"):
            description = getattr(task, "description")
            status_value = getattr(task, "status") or "unknown"
        elif isinstance(task, dict):
            description = str(task.get("description", task))
            status_value = str(task.get("status", "unknown"))
        else:
            description = str(task)
            status_value = "unknown"

        indicator = f"[{status_value}]"

        lines.append(f"{index}. {indicator} {description}")

    task_block = TextBlock(text="\n".join(lines))

    chat_history = chat_history.copy()
    chat_history[-1] = message_copy(chat_history[-1])
    chat_history[-1].blocks.append(task_block)
    return chat_history

def parse_tool_descriptions(tool_list) -> str:
    """Parses the available tools and their descriptions for the system prompt."""
    logger.info("🛠️  Parsing tool descriptions...")
    tool_descriptions = []
    
    for tool in tool_list.values():
        assert callable(tool), f"Tool {tool} is not callable."
        tool_name = tool.__name__
        tool_signature = inspect.signature(tool)
        tool_docstring = tool.__doc__ or "No description available."
        formatted_signature = f"def {tool_name}{tool_signature}:\n    \"\"\"{tool_docstring}\"\"\"\n..."
        tool_descriptions.append(formatted_signature)
        logger.debug(f"  - Parsed tool: {tool_name}")
    descriptions = "\n".join(tool_descriptions)
    logger.info(f"🔩 Found {len(tool_descriptions)} tools.")
    return descriptions


def parse_persona_description(personas) -> str:
    """Parses the available agent personas and their descriptions for the system prompt."""
    logger.debug("👥 Parsing agent persona descriptions for Planner Agent...")
    
    if not personas:
        logger.warning("No agent personas provided to Planner Agent")
        return "No specialized agents available."
    
    persona_descriptions = []
    for persona in personas:
        # Format each persona with name, description, and expertise areas
        expertise_list = ", ".join(persona.expertise_areas) if persona.expertise_areas else "General tasks"
        formatted_persona = f"- **{persona.name}**: {persona.description}\n  Expertise: {expertise_list}"
        persona_descriptions.append(formatted_persona)
        logger.debug(f"  - Parsed persona: {persona.name}")
    
    # Join all persona descriptions into a single string
    descriptions = "\n".join(persona_descriptions)
    logger.debug(f"👤 Found {len(persona_descriptions)} agent personas.")
    return descriptions


def clean_code(code_str: str) -> str:
    """清理代码块中的缩进问题，移除最小公共缩进"""
    if not code_str:
        return ""
    
    # 移除每一行开头的多余空格（如果有的话），但保持相对缩进
    lines = code_str.split('\n')
    if not lines:
        return ""
        
    # 找到最小的公共缩进（忽略空行）
    min_indent = None
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            indent = len(line) - len(stripped)
            if min_indent is None or indent < min_indent:
                min_indent = indent
    
    if min_indent is not None:
        lines = [line[min_indent:] if len(line) >= min_indent else line.lstrip() for line in lines]
        
    return "\n".join(lines).strip()

def extract_code_and_thought(response_text: str) -> Tuple[Optional[str], str]:
    """
    Extracts code and thought from response.
    Supports:
    1. Markdown blocks (```python ... ```)
    2. AutoGLM style <think>...</think> and <answer>...</answer>
    3. autoglm-phone-9b style <[PLHD20...]>...</[PLHD21...]> and <[PLHD41...]>...</[PLHD21...]>
    
    Returns:
        Tuple[Optional[code_string], thought_string]
    """
    logger.debug("✂️ Extracting code and thought from response...")
    
    # 1. 尝试解析 <think> 和 <answer> (AutoGLM 风格)
    think_match = re.search(r"<think>(.*?)</think>", response_text, re.DOTALL)
    answer_match = re.search(r"<answer>(.*?)</answer>", response_text, re.DOTALL)
    
    if think_match or answer_match:
        thoughts = think_match.group(1).strip() if think_match else ""
        answer = answer_match.group(1).strip() if answer_match else ""
        
        # 直接使用 answer 作为代码，因为服务端已经适配了 AutoGLM 动作空间
        if answer.startswith("do(") or answer.startswith("finish("):
            return clean_code(answer), thoughts
        
        # 如果 answer 包含 Python 代码块
        code_pattern = r"```python\s*\n(.*?)\n```"
        code_match = re.search(code_pattern, answer, re.DOTALL)
        if code_match:
            return clean_code(code_match.group(1)), thoughts
            
        return clean_code(answer), thoughts

    # 2. 原有的 Markdown 解析逻辑
    code_pattern = r"```python\s*\n(.*?)\n```"
    code_matches = list(re.finditer(code_pattern, response_text, re.DOTALL))

    if not code_matches:
        # 尝试匹配 do(...) 或 finish(...) 的兜底逻辑（参考 Open-AutoGLM client.py）
        if "finish(message=" in response_text:
            parts = response_text.split("finish(message=", 1)
            action = "finish(message=" + parts[1]
            thought = parts[0].strip()
            return clean_code(action), thought
        
        if "do(action=" in response_text:
            parts = response_text.split("do(action=", 1)
            action = "do(action=" + parts[1]
            thought = parts[0].strip()
            return clean_code(action), thought

        logger.debug("  - No code block found. Entire response is thought.")
        return None, response_text.strip()

    code = "\n".join(clean_code(match.group(1)) for match in code_matches)
    
    # Remove the code blocks from the original text to get the thought
    thought = re.sub(code_pattern, "", response_text, flags=re.DOTALL).strip()
    
    return code, thought