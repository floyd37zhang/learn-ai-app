import logging
import time
from typing import Callable

logger = logging.getLogger("fde-harness")


class Harness:
    def __init__(self, executor: Callable, fallback: Callable = None):
        self.executor = executor
        self.fallback = fallback
    
        
    def run(self, user_input: str) -> dict:
        start_time = time.time()
        try:
            if not user_input or not user_input.strip():
                raise ValueError("用户输入不能为空")
            
            logger.info("开始执行用户输入: %s", user_input[:50])
            result = self.executor(user_input)
            return {
                "code": 0,
                "data": result,
                "cost_ms": int((time.time() - start_time) * 1000)
            }
        except Exception as e:
            logger.error(f"执行器出错: {e}")
            if self.fallback:
                return {
                    "code": 1,
                    "data": self.fallback(e),
                    "cost_ms": int((time.time() - start_time) * 1000)
                }
            
            return {
                "code": 1,
                "data": f"系统繁忙，请稍后重试。错误信息: {str(e)}",
                "cost_ms": int((time.time() - start_time) * 1000)
            }
       
