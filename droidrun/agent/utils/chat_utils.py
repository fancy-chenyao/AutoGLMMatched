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

def _format_ui_elements(ui_data, level=0) -> str:
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
        if index != '':
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
            child_formatted = _format_ui_elements(children, level + 1)
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
            formatted_ui = _format_ui_elements(ui_data)
            
            # If AutoGLM-Phone, use a more concise header
            if persona_name == "AutoGLM-Phone":
                text = f"** UI Elements **\n\n{formatted_ui}"
            else:
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

async def add_screenshot_image_block(screenshot, chat_history: List[ChatMessage], copy = True) -> None:
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
    
    # 1. 尝试解析 autoglm-phone-9b 风格 (PLHD tokens)
    think_match = re.search(r"<\[PLHD20_never_used_51bce0c785ca2f68081bfa7d91973934\]>(.*?)<\[PLHD21_never_used_51bce0c785ca2f68081bfa7d91973934\]>", response_text, re.DOTALL)
    answer_match = re.search(r"<\[PLHD41_never_used_51bce0c785ca2f68081bfa7d91973934\]>(.*?)<\[PLHD21_never_used_51bce0c785ca2f68081bfa7d91973934\]>", response_text, re.DOTALL)
    
    if think_match or answer_match:
        thoughts = think_match.group(1).strip() if think_match else ""
        answer = answer_match.group(1).strip() if answer_match else ""
        
        # 如果 answer 包含 do(...) 格式，尝试将其转换为 python 代码
        if answer.startswith("do(") or answer.startswith("finish("):
            python_code = _convert_autoglm_action_to_python(answer)
            return python_code, thoughts
        
        # 如果 answer 已经是 python 代码块
        code_pattern = r"```python\s*\n(.*?)\n```"
        code_match = re.search(code_pattern, answer, re.DOTALL)
        if code_match:
            return code_match.group(1).strip(), thoughts
            
        return answer, thoughts

    # 2. 尝试解析 <think> 和 <answer> (通用 AutoGLM 风格)
    think_match = re.search(r"<think>(.*?)</think>", response_text, re.DOTALL)
    answer_match = re.search(r"<answer>(.*?)</answer>", response_text, re.DOTALL)
    
    if think_match or answer_match:
        thoughts = think_match.group(1).strip() if think_match else ""
        answer = answer_match.group(1).strip() if answer_match else ""
        
        # 如果 answer 包含 do(...) 格式，尝试将其转换为 python 代码
        if answer.startswith("do(") or answer.startswith("finish("):
            # 简单的转换逻辑：do(action="Tap", element=[x,y]) -> tap(x, y)
            # 这里可以根据需要扩展更复杂的转换
            python_code = _convert_autoglm_action_to_python(answer)
            return python_code, thoughts
        
        # 如果 answer 已经是 python 代码块
        code_pattern = r"```python\s*\n(.*?)\n```"
        code_match = re.search(code_pattern, answer, re.DOTALL)
        if code_match:
            return code_match.group(1).strip(), thoughts
            
        return answer, thoughts

    # 2. 原有的 Markdown 解析逻辑
    code_pattern = r"^\s*```python\s*\n(.*?)\n^\s*```\s*?$"
    code_matches = list(re.finditer(code_pattern, response_text, re.DOTALL | re.MULTILINE))

    if not code_matches:
        logger.debug("  - No code block found. Entire response is thought.")
        return None, response_text.strip()

    code = "\n".join(match.group(1).strip() for match in code_matches)
    
    # Remove the code blocks from the original text to get the thought
    thought = re.sub(code_pattern, "", response_text, flags=re.DOTALL | re.MULTILINE).strip()
    
    return code, thought

def _convert_autoglm_action_to_python(action_str: str) -> str:
    """将 AutoGLM 的 do(action=...) 格式转换为 Python 代码"""
    # 示例: do(action="Tap", element=[500,500]) -> tap(element=[500,500])
    # 示例: finish(message="done") -> complete(success=True, reason="done")
    
    if action_str.startswith("finish("):
        msg_match = re.search(r'message=["\'](.*?)["\']', action_str)
        msg = msg_match.group(1) if msg_match else "Task completed"
        return f'complete(success=True, reason="{msg}")'
        
    if action_str.startswith("do("):
        action_match = re.search(r'action=["\'](.*?)["\']', action_str)
        if not action_match:
            return action_str
            
        action = action_match.group(1).lower()
        
        if action == "tap":
            coord_match = re.search(r'element=\[(.*?)\]', action_str)
            msg_match = re.search(r'message=["\'](.*?)["\']', action_str)
            if coord_match:
                result = f"tap(element=[{coord_match.group(1)}])"
                if msg_match:
                    logger.info(f"AutoGLM important action message: {msg_match.group(1)}")
                return result
        elif action == "type" or action == "type_name":
            text_match = re.search(r'text=["\'](.*?)["\']', action_str)
            if text_match:
                return f'input_text("{text_match.group(1)}")'
        elif action == "swipe":
            start_match = re.search(r'start=\[(.*?)\]', action_str)
            end_match = re.search(r'end=\[(.*?)\]', action_str)
            if start_match and end_match:
                return f"swipe(start=[{start_match.group(1)}], end=[{end_match.group(1)}])"
        elif action == "back":
            return "back()"
        elif action == "home":
            return "home()"
        elif action == "launch":
            app_match = re.search(r'app=["\'](.*?)["\']', action_str)
            if app_match:
                return f'start_app("{app_match.group(1)}")'
        elif action == "wait":
            duration_match = re.search(r'duration=["\'](\d+).*?["\']', action_str)
            if duration_match:
                return f'wait("{duration_match.group(1)} seconds")'
            return 'wait("2 seconds")'
        elif action == "double tap":
            coord_match = re.search(r'element=\[(.*?)\]', action_str)
            if coord_match:
                return f"double_tap(element=[{coord_match.group(1)}])"
        elif action == "long press":
            coord_match = re.search(r'element=\[(.*?)\]', action_str)
            if coord_match:
                return f"long_press(element=[{coord_match.group(1)}])"
        elif action == "take_over":
            msg_match = re.search(r'message=["\'](.*?)["\']', action_str)
            msg = msg_match.group(1) if msg_match else "Need user assistance"
            return f'take_over(message="{msg}")'
        elif action == "interact":
            return 'interact()'
        elif action == "note":
            msg_match = re.search(r'message=["\'](.*?)["\']', action_str)
            msg = msg_match.group(1) if msg_match else ""
            return f'note(message="{msg}")'
        elif action == "call_api":
            inst_match = re.search(r'instruction=["\'](.*?)["\']', action_str)
            inst = inst_match.group(1) if inst_match else ""
            return f'call_api(instruction="{inst}")'
                
    return action_str