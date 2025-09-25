/*
 * Copyright (c) 2025 PoCEffectiveness
 * All rights reserved.
 */


class Color:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"

    @staticmethod
    def colorize(msg: str, color_code: str) -> str:
        return f"{color_code}{msg}{Color.RESET}"

    @staticmethod
    def success(msg: str) -> str:
        return Color.colorize(msg, Color.GREEN)

    @staticmethod
    def info(msg: str) -> str:
        return Color.colorize(msg, Color.CYAN)

    @staticmethod
    def warning(msg: str) -> str:
        return Color.colorize(msg, Color.YELLOW)

    @staticmethod
    def error(msg: str) -> str:
        return Color.colorize(msg, Color.RED)

    @staticmethod
    def bold(msg: str) -> str:
        return Color.colorize(msg, Color.BOLD)


def log(component: str, message: str, level: str = "info") -> None:
    level = level.lower()
    prefix = f"[{component}] "
    colored_msg = message

    if level == "success":
        colored_msg = Color.success(prefix + message)
    elif level == "info":
        colored_msg = Color.info(prefix + message)
    elif level == "warning":
        colored_msg = Color.warning(prefix + message)
    elif level == "error":
        colored_msg = Color.error(prefix + message)
    elif level == "bold":
        colored_msg = Color.bold(prefix + message)
    else:
        # 默认不加颜色
        colored_msg = prefix + message

    print(colored_msg)
