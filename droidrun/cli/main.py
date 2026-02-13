"""
DroidRun CLI - Command line interface for controlling Android devices through LLM agents.
"""

import asyncio
import click
import os
import logging
import warnings
from contextlib import nullcontext
from dotenv import load_dotenv
from rich.console import Console
from droidrun.agent.droid import DroidAgent
from droidrun.agent.utils.llm_picker import load_llm
from droidrun.tools import IOSTools, WebSocketTools
from droidrun.server import get_global_server
from droidrun.config import get_config_manager
from droidrun.agent.context.personas import DEFAULT, BIG_AGENT
from functools import wraps
from droidrun.cli.logs import LogHandler
from droidrun.telemetry import print_telemetry_message
from droidrun.macro.cli import macro_cli

# Load environment variables from .env file
load_dotenv()

# Suppress all warnings
warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "false"

console = Console()


def configure_logging(goal: str, debug: bool):
    logger = logging.getLogger("droidrun")
    logger.handlers = []

    handler = LogHandler(goal)
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s %(message)s", "%H:%M:%S")
        if debug
        else logging.Formatter("%(message)s", "%H:%M:%S")
    )
    logger.addHandler(handler)

    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False

    if debug:
        tools_logger = logging.getLogger("droidrun-tools")
        tools_logger.addHandler(handler)
        tools_logger.propagate = False
        tools_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    return handler


def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


@coro
async def run_command(
    command: str,
    device: str | None,
    provider: str,
    model: str,
    steps: int,
    base_url: str,
    api_base: str,
    vision: bool,
    reasoning: bool,
    reflection: bool,
    tracing: bool,
    debug: bool,
    save_trajectory: str = "none",
    ios: bool = False,
    allow_drag: bool = False,
    # 新增记忆系统参数
    enable_memory: bool = True,
    memory_threshold: float = 0.8,
    memory_storage: str = "experiences",
    disable_hot_start: bool = False,
    disable_parameter_adaptation: bool = False,
    disable_monitoring: bool = False,
    **kwargs,
):
    """Run a command on your Android device using natural language."""
    log_handler = configure_logging(command, debug)
    logger = logging.getLogger("droidrun")

    log_handler.update_step("Initializing...")

    with log_handler.render() as live:
        try:
            logger.info(f"🚀 Starting: {command}")
            print_telemetry_message()

            if not kwargs.get("temperature"):
                kwargs["temperature"] = 0

            log_handler.update_step("Setting up tools...")

            # 获取配置管理器（用于检查服务器模式）
            config_manager = get_config_manager()
            server_config = config_manager.get_server_config()
            
            # 必须使用 WebSocket 服务端模式（已移除原有 AdbTools 逻辑）
            logger.info("🌐 使用 WebSocket 服务端模式")
            
            # 获取已运行的服务器实例
            server = get_global_server()
            if not server:
                raise ValueError(
                    "WebSocket 服务器未运行。请先启动服务器：\n"
                    "  droidrun server\n"
                    "或：\n"
                    "  python server.py"
                )
            
            # 查询已连接设备
            connected_devices = server.get_connected_devices()
            
            # 解析设备ID
            if device:
                # 使用指定的设备ID
                if device not in connected_devices:
                    raise ValueError(
                        f"设备 '{device}' 未连接到服务器。\n"
                        f"已连接设备: {connected_devices if connected_devices else '无'}\n"
                        f"请先启动APP并连接到服务器。"
                    )
                device_id = device
                logger.info(f"📱 使用指定设备: {device_id}")
            elif connected_devices:
                # 使用第一个已连接设备
                device_id = list(connected_devices)[0]
                logger.info(f"📱 使用已连接设备: {device_id}")
                if len(connected_devices) > 1:
                    logger.info(f"   其他已连接设备: {list(connected_devices)[1:]}")
            else:
                raise ValueError(
                    "没有设备连接到服务器。\n"
                    "请先启动APP并连接到服务器。\n"
                    f"服务器地址: ws://{server_config.server_host}:{server_config.server_port}{server_config.websocket_path}"
                )
            
            # 创建 WebSocketTools
            tools = WebSocketTools(
                device_id=device_id,
                session_manager=server.session_manager,
                config_manager=config_manager,
                timeout=server_config.timeout,
            )
            
            # 注册工具实例到服务器（用于响应处理）
            server.register_tools_instance(device_id, tools)
            
            logger.info(f"✅ WebSocketTools 已创建 (设备ID: {device_id})")

            # Set excluded tools based on CLI flags
            excluded_tools = [] if allow_drag else ["drag"]

            # Select personas based on --drag flag
            personas = [BIG_AGENT] if allow_drag else [DEFAULT]

            # LLM setup
            log_handler.update_step("Initializing LLM...")
            llm = load_llm(
                provider_name=provider,
                model=model,
                base_url=base_url,
                api_base=api_base,
                **kwargs,
            )
            logger.info(f"🧠 LLM ready: {provider}/{model}")

            # Agent setup
            log_handler.update_step("Initializing DroidAgent...")

            mode = "planning with reasoning" if reasoning else "direct execution"
            logger.info(f"🤖 Agent mode: {mode}")

            if tracing:
                logger.info("🔍 Tracing enabled")

            # 创建记忆配置
            from droidrun.agent.context.memory_config import create_memory_config
            memory_config = create_memory_config(
                enabled=enable_memory,
                similarity_threshold=memory_threshold,
                storage_dir=memory_storage,
                hot_start_enabled=not disable_hot_start,
                parameter_adaptation_enabled=not disable_parameter_adaptation,
                monitoring_enabled=not disable_monitoring,
            )

            droid_agent = DroidAgent(
                goal=command,
                llm=llm,
                tools=tools,
                personas=personas,
                excluded_tools=excluded_tools,
                max_steps=steps,
                timeout=1000,
                vision=vision,
                reasoning=reasoning,
                reflection=reflection,
                enable_tracing=tracing,
                debug=debug,
                save_trajectories=save_trajectory,
                # 新增记忆系统参数
                enable_memory=enable_memory,
                memory_similarity_threshold=memory_threshold,
                memory_storage_dir=memory_storage,
                memory_config=memory_config,
                # 传递配置管理器（用于服务端模式等）
                config_manager=config_manager,
            )

            logger.info("▶️  Starting agent execution...")
            logger.info("Press Ctrl+C to stop")
            log_handler.update_step("Running agent...")

            try:
                handler = droid_agent.run()

                async for event in handler.stream_events():
                    log_handler.handle_event(event)
                result = await handler

            except KeyboardInterrupt:
                log_handler.is_completed = True
                log_handler.is_success = False
                log_handler.current_step = "Stopped by user"
                logger.info("⏹️ Stopped by user")

            except Exception as e:
                log_handler.is_completed = True
                log_handler.is_success = False
                log_handler.current_step = f"Error: {e}"
                logger.error(f"💥 Error: {e}")
                if debug:
                    import traceback

                    logger.debug(traceback.format_exc())

        except Exception as e:
            log_handler.current_step = f"Error: {e}"
            logger.error(f"💥 Setup error: {e}")
            if debug:
                import traceback

                logger.debug(traceback.format_exc())


class DroidRunCLI(click.Group):
    def parse_args(self, ctx, args):
        # If the first arg is not an option and not a known command, treat as 'run'
        if args and """not args[0].startswith("-")""" and args[0] not in self.commands:
            args.insert(0, "run")

        return super().parse_args(ctx, args)


@click.option("--device", "-d", help="Device serial number or IP address", default=None)
@click.option(
    "--provider",
    "-p",
    help="LLM provider (OpenAI, Ollama, Anthropic, GoogleGenAI, DeepSeek)",
    default="GoogleGenAI",
)
@click.option(
    "--model",
    "-m",
    help="LLM model name",
    default="models/gemini-2.5-flash",
)
@click.option("--temperature", type=float, help="Temperature for LLM", default=0.2)
@click.option("--steps", type=int, help="Maximum number of steps", default=15)
@click.option(
    "--base_url",
    "-u",
    help="Base URL for API (e.g., OpenRouter or Ollama)",
    default=None,
)
@click.option(
    "--api_base",
    help="Base URL for API (e.g., OpenAI, OpenAI-Like)",
    default=None,
)
@click.option(
    "--vision",
    is_flag=True,
    help="Enable vision capabilites by using screenshots",
    default=False,
)
@click.option(
    "--reasoning", is_flag=True, help="Enable planning with reasoning", default=False
)
@click.option(
    "--reflection",
    is_flag=True,
    help="Enable reflection step for higher reasoning",
    default=False,
)
@click.option(
    "--tracing", is_flag=True, help="Enable Arize Phoenix tracing", default=False
)
@click.option(
    "--debug", is_flag=True, help="Enable verbose debug logging", default=False
)
@click.option(
    "--save-trajectory",
    type=click.Choice(["none", "step", "action"]),
    help="Trajectory saving level: none (no saving), step (save per step), action (save per action)",
    default="none",
)
# 新增记忆系统参数
@click.option(
    "--enable-memory",
    is_flag=True,
    default=True,
    help="Enable memory system for experience learning and hot start",
)
@click.option(
    "--memory-threshold",
    type=float,
    default=0.8,
    help="Memory similarity threshold for hot start (0.0-1.0)",
)
@click.option(
    "--memory-storage",
    type=str,
    default="experiences",
    help="Directory to store memory experiences",
)
@click.option(
    "--disable-hot-start",
    is_flag=True,
    help="Disable hot start functionality",
)
@click.option(
    "--disable-parameter-adaptation",
    is_flag=True,
    help="Disable parameter adaptation for hot start",
)
@click.option(
    "--disable-monitoring",
    is_flag=True,
    help="Disable execution monitoring and fallback",
)
@click.group(cls=DroidRunCLI)
def cli(
    device: str | None,
    provider: str,
    model: str,
    steps: int,
    base_url: str,
    api_base: str,
    temperature: float,
    vision: bool,
    reasoning: bool,
    reflection: bool,
    tracing: bool,
    debug: bool,
    save_trajectory: str = "none",
    # 新增记忆系统参数
    enable_memory: bool = True,
    memory_threshold: float = 0.8,
    memory_storage: str = "experiences",
    disable_hot_start: bool = False,
    disable_parameter_adaptation: bool = False,
    disable_monitoring: bool = False,
):
    """DroidRun - Control your Android device through LLM agents."""
    pass


@cli.command()
@click.argument("command", type=str)
@click.option("--device", "-d", help="Device serial number or IP address", default=None)
@click.option(
    "--provider",
    "-p",
    help="LLM provider (OpenAI, Ollama, Anthropic, GoogleGenAI, DeepSeek)",
    default="GoogleGenAI",
)
@click.option(
    "--model",
    "-m",
    help="LLM model name",
    default="models/gemini-2.5-flash",
)
@click.option("--temperature", type=float, help="Temperature for LLM", default=0.2)
@click.option("--steps", type=int, help="Maximum number of steps", default=15)
@click.option(
    "--base_url",
    "-u",
    help="Base URL for API (e.g., OpenRouter or Ollama)",
    default=None,
)
@click.option(
    "--api_base",
    help="Base URL for API (e.g., OpenAI or OpenAI-Like)",
    default=None,
)
@click.option(
    "--vision",
    is_flag=True,
    help="Enable vision capabilites by using screenshots",
    default=False,
)
@click.option(
    "--reasoning", is_flag=True, help="Enable planning with reasoning", default=False
)
@click.option(
    "--reflection",
    is_flag=True,
    help="Enable reflection step for higher reasoning",
    default=False,
)
@click.option(
    "--tracing", is_flag=True, help="Enable Arize Phoenix tracing", default=False
)
@click.option(
    "--debug", is_flag=True, help="Enable verbose debug logging", default=False
)
@click.option(
    "--save-trajectory",
    type=click.Choice(["none", "step", "action"]),
    help="Trajectory saving level: none (no saving), step (save per step), action (save per action)",
    default="none",
)
@click.option(
    "--drag",
    "allow_drag",
    is_flag=True,
    help="Enable drag tool",
    default=False,
)
@click.option("--ios", is_flag=True, help="Run on iOS device", default=False)
@click.pass_context
def run(
    ctx,
    command: str,
    device: str | None,
    provider: str,
    model: str,
    steps: int,
    base_url: str,
    api_base: str,
    temperature: float,
    vision: bool,
    reasoning: bool,
    reflection: bool,
    tracing: bool,
    debug: bool,
    save_trajectory: str,
    allow_drag: bool,
    ios: bool,
):
    """Run a command on your Android device using natural language."""
    # 从父上下文（group）获取记忆系统参数
    parent = ctx.parent
    enable_memory = parent.params.get("enable_memory", True) if parent else True
    memory_threshold = parent.params.get("memory_threshold", 0.8) if parent else 0.8
    memory_storage = parent.params.get("memory_storage", "experiences") if parent else "experiences"
    disable_hot_start = parent.params.get("disable_hot_start", False) if parent else False
    disable_parameter_adaptation = parent.params.get("disable_parameter_adaptation", False) if parent else False
    disable_monitoring = parent.params.get("disable_monitoring", False) if parent else False
    
    # Call our standalone function
    return run_command(
        command,
        device,
        provider,
        model,
        steps,
        base_url,
        api_base,
        vision,
        reasoning,
        reflection,
        tracing,
        debug,
        temperature=temperature,
        save_trajectory=save_trajectory,
        allow_drag=allow_drag,
        ios=ios,
        # 传递记忆系统参数
        enable_memory=enable_memory,
        memory_threshold=memory_threshold,
        memory_storage=memory_storage,
        disable_hot_start=disable_hot_start,
        disable_parameter_adaptation=disable_parameter_adaptation,
        disable_monitoring=disable_monitoring,
    )


# Add macro commands as a subgroup
cli.add_command(macro_cli, name="macro")

# Add server command
from droidrun.server.server_cli import server_cli
cli.add_command(server_cli, name="server")


if __name__ == "__main__":
    command = "Open the settings app"
    device = None
    provider = "GoogleGenAI"
    model = "models/gemini-2.5-flash"
    temperature = 0
    api_key = os.getenv("GOOGLE_API_KEY")
    steps = 15
    vision = True
    reasoning = True
    reflection = False
    tracing = True
    debug = True
    base_url = None
    api_base = None
    ios = False
    save_trajectory = "action"
    allow_drag = False
    run_command(
        command=command,
        device=device,
        provider=provider,
        model=model,
        steps=steps,
        temperature=temperature,
        vision=vision,
        reasoning=reasoning,
        reflection=reflection,
        tracing=tracing,
        debug=debug,
        base_url=base_url,
        api_base=api_base,
        api_key=api_key,
        allow_drag=allow_drag,
        ios=ios,
        save_trajectory=save_trajectory,
    )
