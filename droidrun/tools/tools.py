from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import logging
from typing import Tuple, Dict, Callable, Any, Optional
from functools import wraps
import sys

# Get a logger for this module
logger = logging.getLogger(__name__)


class Tools(ABC):
    """
    Abstract base class for all tools.
    This class provides a common interface for all tools to implement.
    """

    @staticmethod
    def ui_action(func):
        """
        Decorator to capture screenshots and UI states for actions that modify the UI.
        Now supports async functions.
        """
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            self = args[0]
            result = await func(*args, **kwargs)
            
            # Check if save_trajectories attribute exists and is set to "action"
            if hasattr(self, 'save_trajectories') and self.save_trajectories == "action":
                frame = sys._getframe(1)
                caller_globals = frame.f_globals
                
                step_screenshots = caller_globals.get('step_screenshots')
                step_ui_states = caller_globals.get('step_ui_states')
                
                # For async tools, we should use async methods if available
                if hasattr(self, 'get_state_async'):
                    if step_screenshots is not None:
                        # Use async screenshot if available
                        if hasattr(self, 'take_screenshot_async'):
                            step_screenshots.append((await self.take_screenshot_async())[1])
                        else:
                            step_screenshots.append(self.take_screenshot()[1])
                    if step_ui_states is not None:
                        step_ui_states.append(await self.get_state_async())
                else:
                    # Fallback to sync methods
                    if step_screenshots is not None:
                        step_screenshots.append(self.take_screenshot()[1])
                    if step_ui_states is not None:
                        step_ui_states.append(self.get_state())
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            self = args[0]
            result = func(*args, **kwargs)
            
            # Check if save_trajectories attribute exists and is set to "action"
            if hasattr(self, 'save_trajectories') and self.save_trajectories == "action":
                frame = sys._getframe(1)
                caller_globals = frame.f_globals
                
                step_screenshots = caller_globals.get('step_screenshots')
                step_ui_states = caller_globals.get('step_ui_states')
                
                # 避免在事件循环线程内调用同步方法导致阻塞：
                # 若工具实现了异步API（如 get_state_async），则不在装饰器里执行同步截图/取状态
                if not hasattr(self, 'get_state_async'):
                    if step_screenshots is not None:
                        step_screenshots.append(self.take_screenshot()[1])
                    if step_ui_states is not None:
                        step_ui_states.append(self.get_state())
            return result
        
        # Return appropriate wrapper based on whether function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    @abstractmethod
    async def get_state(self) -> Dict[str, Any]:
        """
        Get the current state of the tool.
        """
        pass

    @abstractmethod
    async def tap_by_index(self, index: int) -> str:
        """
        Tap the element at the given index.
        """
        pass

    async def tap(self, element: Optional[List[int]] = None, index: Optional[int] = None) -> str:
        """
        Tap at coordinates or by element index.
        """
        raise NotImplementedError()

    async def double_tap(self, element: Optional[List[int]] = None, index: Optional[int] = None) -> str:
        """
        Double tap at coordinates or by element index.
        """
        raise NotImplementedError()

    async def long_press(self, element: Optional[List[int]] = None, index: Optional[int] = None, duration_ms: int = 1000) -> str:
        """
        Long press at coordinates or by element index.
        """
        raise NotImplementedError()

    async def home(self) -> str:
        """
        Press the home button.
        """
        raise NotImplementedError()

    async def wait(self, duration: str) -> str:
        """
        Wait for a specified duration.
        """
        raise NotImplementedError()

    async def take_over(self, message: str) -> str:
        """
        Request user take over.
        """
        raise NotImplementedError()

    async def note(self, message: str) -> str:
        """
        Record a note.
        """
        raise NotImplementedError()

    async def call_api(self, instruction: str) -> str:
        """
        Call an external API or perform a complex instruction.
        """
        raise NotImplementedError()

    async def interact(self) -> str:
        """
        Request user interaction for choices.
        """
        raise NotImplementedError()

    @abstractmethod
    async def swipe(
        self, start: List[int], end: List[int], duration_ms: int = 300
    ) -> bool:
        """
        Swipe from the given start coordinates to the given end coordinates.
        """
        pass

    @abstractmethod
    async def drag(
        self, start: List[int], end: List[int], duration_ms: int = 3000
    ) -> bool:
        """
        Drag from the given start coordinates to the given end coordinates.
        """
        pass

    @abstractmethod
    async def input_text(self, text: str, element: Optional[List[int]] = None, index: Optional[int] = None) -> str:
        """
        Input the given text into an input field.
        """
        pass

    @abstractmethod
    async def back(self) -> str:
        """
        Press the back button.
        """
        pass

    @abstractmethod
    async def press_key(self, keycode: int) -> str:
        """
        Enter the given keycode.
        """
        pass

    @abstractmethod
    async def start_app(self, package: str, activity: str = "") -> str:
        """
        Start the given app.
        """
        pass

    @abstractmethod
    async def take_screenshot(self, hide_overlay: bool = True) -> Tuple[str, bytes]:
        """
        Take a screenshot of the device.
        """
        pass

    @abstractmethod
    async def list_packages(self, include_system_apps: bool = False) -> List[str]:
        """
        List all packages on the device.
        """
        pass

    @abstractmethod
    async def remember(self, information: str) -> str:
        """
        Remember the given information. This is used to store information in the tool's memory.
        """
        pass

    @abstractmethod
    async def get_memory(self) -> List[str]:
        """
        Get the memory of the tool.
        """
        pass

    @abstractmethod
    async def complete(self, success: bool, reason: str = "") -> None:
        """
        Complete the tool. This is used to indicate that the tool has completed its task.
        """
        pass

    async def home(self) -> str:
        """
        Press the home button.
        """
        return await self.press_key(3)  # Default Android Home keycode

    async def wait(self, duration: str = "2 seconds") -> str:
        """
        Wait for a specified duration.
        """
        try:
            seconds = float(duration.split()[0])
        except (ValueError, IndexError):
            seconds = 2.0
        await asyncio.sleep(seconds)
        return f"Waited for {seconds} seconds"

    async def interact(self) -> str:
        """
        Trigger an interaction when multiple options are available.
        """
        return "Interaction triggered. Please specify your choice."

    async def note(self, message: str) -> str:
        """
        Record information about the current page.
        """
        return f"Note recorded: {message}"

    async def call_api(self, instruction: str) -> str:
        """
        Call an AI API to summarize or comment on the current page.
        """
        return f"API called with instruction: {instruction}"

    async def take_over(self, message: str) -> str:
        """
        Request user assistance for login or verification.
        """
        return f"Take over requested: {message}"

    async def double_tap(self, element: Optional[List[int]] = None, index: Optional[int] = None) -> str:
        """
        Double tap on a specific point or element.
        """
        # Default implementation: two taps
        await self.tap(element=element, index=index)
        await asyncio.sleep(0.1)
        return await self.tap(element=element, index=index)

    async def long_press(self, element: Optional[List[int]] = None, index: Optional[int] = None, duration_ms: int = 1000) -> str:
        """
        Long press on a specific point or element.
        """
        # Default implementation: use drag with same start and end
        if element:
            await self.drag(start=element, end=element, duration_ms=duration_ms)
            return f"Long pressed at {element}"
        return "Long press failed: no element or index provided"

    # --- AutoGLM Compatible Methods ---

    async def do(self, action: str, **kwargs) -> Any:
        """
        AutoGLM style action dispatcher. Execute a single operation on the device.
        
        Args:
            action: The type of action (e.g., "Launch", "Tap", "Type", "Swipe", "Back", "Home", "Wait").
            **kwargs: Action-specific arguments (e.g., app="Name", element=[x,y], text="txt", start=[x,y], end=[x,y]).
            
        Examples:
            do(action="Tap", element=[500,500])
            do(action="Launch", app="Settings")
            do(action="Type", text="Hello")
        """
        action_lower = action.lower().replace(" ", "").replace("_", "")
        
        if action_lower == "tap":
            return await self.Tap(**kwargs)
        elif action_lower in ["type", "inputtext", "typename"]:
            return await self.Type(**kwargs)
        elif action_lower == "swipe":
            return await self.Swipe(**kwargs)
        elif action_lower == "back":
            return await self.Back(**kwargs)
        elif action_lower == "home":
            return await self.Home(**kwargs)
        elif action_lower == "wait":
            return await self.Wait(**kwargs)
        elif action_lower == "doubletap":
            return await self.DoubleTap(**kwargs)
        elif action_lower == "longpress":
            return await self.LongPress(**kwargs)
        elif action_lower == "scroll":
            # Map scroll to swipe if not explicitly implemented
            direction = kwargs.get("direction", "down").lower()
            if direction == "down":
                return await self.Swipe(start=[500, 800], end=[500, 200])
            elif direction == "up":
                return await self.Swipe(start=[500, 200], end=[500, 800])
            elif direction == "left":
                return await self.Swipe(start=[800, 500], end=[200, 500])
            elif direction == "right":
                return await self.Swipe(start=[200, 500], end=[800, 500])
        elif action_lower == "drag":
            return await self.Drag(**kwargs)
        elif action_lower in ["launch", "startapp"]:
            app = kwargs.get("app") or kwargs.get("package")
            if app:
                return await self.Launch(app=app)
        elif action_lower == "takeover":
            return await self.TakeOver(**kwargs)
        elif action_lower == "interact":
            return await self.Interact(**kwargs)
        elif action_lower == "note":
            return await self.Note(**kwargs)
        elif action_lower == "callapi":
            return await self.CallApi(**kwargs)
            
        raise ValueError(f"Unknown AutoGLM action: {action}")

    async def finish(self, message: str = "") -> None:
        """
        AutoGLM style finish action to terminate the program and optionally print a message.
        e.g. finish(message="Task completed.")
        """
        await self.complete(success=True, reason=message)

    # Individual AutoGLM actions as methods (capitalized)
    async def Tap(self, element: Optional[List[int]] = None, index: Optional[int] = None, **kwargs) -> str:
        # Support both element and index as in AutoGLM
        idx = index or kwargs.get("index")
        elem = element or kwargs.get("element")
        return await self.tap(element=elem, index=idx)

    async def Swipe(self, start: List[int], end: List[int], duration_ms: int = 300, **kwargs) -> bool:
        return await self.swipe(start=start, end=end, duration_ms=duration_ms)

    async def InputText(self, text: str = "", element: Optional[List[int]] = None, index: Optional[int] = None, **kwargs) -> str:
        txt = text or kwargs.get("text", "")
        idx = index or kwargs.get("index")
        elem = element or kwargs.get("element")
        return await self.input_text(text=txt, element=elem, index=idx)
    
    async def Type(self, text: str = "", **kwargs) -> str:
        txt = text or kwargs.get("text", "")
        return await self.input_text(text=txt)

    async def Back(self, **kwargs) -> str:
        return await self.back()

    async def Home(self, **kwargs) -> str:
        return await self.home()

    async def Wait(self, duration: str = "2 seconds", **kwargs) -> str:
        dur = duration or kwargs.get("duration", "2 seconds")
        return await self.wait(duration=dur)

    async def DoubleTap(self, element: Optional[List[int]] = None, index: Optional[int] = None, **kwargs) -> str:
        idx = index or kwargs.get("index")
        elem = element or kwargs.get("element")
        return await self.double_tap(element=elem, index=idx)

    async def LongPress(self, element: Optional[List[int]] = None, index: Optional[int] = None, duration_ms: int = 1000, **kwargs) -> str:
        idx = index or kwargs.get("index")
        elem = element or kwargs.get("element")
        dur = duration_ms or kwargs.get("duration_ms", 1000)
        return await self.long_press(element=elem, index=idx, duration_ms=dur)

    async def Drag(self, start: List[int], end: List[int], duration_ms: int = 3000, **kwargs) -> bool:
        return await self.drag(start=start, end=end, duration_ms=duration_ms)

    async def Launch(self, app: str = "", **kwargs) -> str:
        pkg = app or kwargs.get("app") or kwargs.get("package", "")
        return await self.start_app(package=pkg)
    
    async def TakeOver(self, message: str = "", **kwargs) -> str:
        msg = message or kwargs.get("message", "")
        return await self.take_over(message=msg)

    async def Interact(self, **kwargs) -> str:
        return await self.interact()

    async def Note(self, message: str = "", **kwargs) -> str:
        msg = message or kwargs.get("message", "")
        return await self.note(message=msg)

    async def CallApi(self, instruction: str = "", **kwargs) -> str:
        inst = instruction or kwargs.get("instruction", "")
        return await self.call_api(instruction=inst)
    
    async def ask_user(
        self,
        question: str,
        question_type: str = "text",
        options: Optional[List[str]] = None,
        default_value: Optional[str] = None,
        timeout_seconds: float = 60.0,
    ) -> str:
        """
        Ask the user a question and wait for their response.
        
        IMPORTANT: This should be used as a LAST RESORT ONLY!
        Before calling ask_user(), you must:
        - Try scrolling to see if missing fields appear
        - Click "Next", "Confirm", "Continue" buttons to check for additional pages
        - Explore all tabs, expandable sections, or navigation options
        - Verify there's no programmatic way to proceed
        
        Only use ask_user() when:
        - You've exhausted ALL UI exploration options
        - Information is genuinely ambiguous and requires user clarification
        - The app requires external information not available in the UI
        
        Args:
            question: The question to ask the user
            question_type: Type of question - "text", "choice", or "confirm"
            options: List of options for "choice" type questions
            default_value: Default value if user doesn't respond
            timeout_seconds: Timeout in seconds
        
        Returns:
            The user's answer as a string
        
        Note:
            This is a default implementation that raises NotImplementedError.
            Subclasses like WebSocketTools should override this method to provide actual functionality.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support interactive user questions. "
            "This feature is only available when using WebSocket-based tools."
        )


def describe_tools(tools: Tools, exclude_tools: Optional[List[str]] = None) -> Dict[str, Callable[..., Any]]:
    """
    Describe the tools available for the given Tools instance.

    Args:
        tools: The Tools instance to describe.
        exclude_tools: List of tool names to exclude from the description.

    Returns:
        A dictionary mapping tool names to their descriptions.
    """
    exclude_tools = exclude_tools or []

    description = {
        # UI interaction
        "swipe": tools.swipe,
        "input_text": tools.input_text,
        "press_key": tools.press_key,
        "tap_by_index": tools.tap_by_index,
        "drag": tools.drag,
        "tap": tools.tap,
        # App management
        "start_app": tools.start_app,
        "list_packages": tools.list_packages,
        # state management
        "remember": tools.remember,
        "complete": tools.complete,
        # User interaction (Phase 3: Interactive Execution)
        "ask_user": tools.ask_user,
        
        # --- AutoGLM Compatible Actions ---
        "do": tools.do,
        "finish": tools.finish,
        "Tap": tools.Tap,
        "Swipe": tools.Swipe,
        "InputText": tools.InputText,
        "Type": tools.Type,
        "Back": tools.Back,
        "Home": tools.Home,
        "Wait": tools.Wait,
        "DoubleTap": tools.DoubleTap,
        "LongPress": tools.LongPress,
        "Drag": tools.Drag,
        "Launch": tools.Launch,
        "TakeOver": tools.TakeOver,
        "Interact": tools.Interact,
        "Note": tools.Note,
        "CallApi": tools.CallApi,
    }

    # Remove excluded tools
    for tool_name in exclude_tools:
        description.pop(tool_name, None)

    return description
