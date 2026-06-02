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


class ReadAttachmentContent(BaseTool):
    name = "read_attachment_content"
    description = "Fetches the full raw text content of an uploaded user file attachment from the secure database using its unique object key. This tool is used to retrieve the content of documents that have been uploaded and processed, allowing the agent to read and analyze the text for answering user queries or performing tasks based on the document's information."
    parameters = {
        "type": "object",
        "properties": {
            "file_name": {
                "type": "string",
                "description": "The name of the file attachment, including its extension, found inside the file-name attribute of the <attachment /> tag.",
            },
            "object_key": {
                "type": "string",
                "description": "The unique identifier string found inside the object-key attribute of the <attachment /> tag.",
            }
        },
        "required": ["object_key"],
    }
    async def execute(self, object_key: str, **kwargs) -> str:
        # Placeholder implementation - in a real implementation, this would read the file content
        return f"[Stub] Content of '{object_key}' would be returned here."   

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
