import ast
import operator
from app.tools.base import BaseTool

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPS:
            raise ValueError(f"Unsupported operator: {op_type}")
        return _SAFE_OPS[op_type](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_safe_eval(node.operand)
    raise ValueError(f"Unsupported expression: {type(node)}")


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluates a mathematical expression and returns the numeric result."
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "A mathematical expression to evaluate, e.g. '2 + 3 * 4'",
            }
        },
        "required": ["expression"],
    }

    async def execute(self, expression: str, **kwargs) -> str:
        try:
            tree = ast.parse(expression, mode="eval")
            result = _safe_eval(tree.body)
            return str(result)
        except Exception as e:
            return f"Error: {e}"


class WebSearchStubTool(BaseTool):
    name = "web_search"
    description = "Searches the web for information. Returns stub results (not connected to a real search engine)."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            }
        },
        "required": ["query"],
    }

    async def execute(self, query: str, **kwargs) -> str:
        return f"[Stub] Search results for '{query}': No real search engine connected. Configure a real search API to enable this tool."
