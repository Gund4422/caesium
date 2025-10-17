import inspect
import ast
from pathlib import Path
import struct

# -----------------------------
# Utilities
# -----------------------------
def align(value, alignment):
    """Align a value to the given power-of-2 alignment."""
    return (value + (alignment - 1)) & ~(alignment - 1)

def float_to_hex(f):
    """Convert Python float to 64-bit hex for assembly."""
    return hex(struct.unpack("<Q", struct.pack("<d", f))[0])

def chunk_list(lst, n):
    """Yield successive n-sized chunks from list."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# -----------------------------
# Registers
# -----------------------------
XMM_REGS = ["xmm{}".format(i) for i in range(16)]
GENERAL_REGS = ["rdi","rsi","rdx","rcx","r8","r9"]

class RegisterAllocator:
    """Tracks used XMM registers."""
    def __init__(self):
        self.free_xmm = XMM_REGS.copy()
        self.used_xmm = {}
    def allocate_xmm(self, name):
        if name in self.used_xmm:
            return self.used_xmm[name]
        if not self.free_xmm:
            raise RuntimeError("Ran out of XMM registers!")
        reg = self.free_xmm.pop(0)
        self.used_xmm[name] = reg
        return reg
    def free_all(self):
        self.free_xmm = XMM_REGS.copy()
        self.used_xmm.clear()

# -----------------------------
# ASM Generator
# -----------------------------
class ASMGenerator(ast.NodeVisitor):
    def __init__(self, func_name, args):
        self.func_name = func_name
        self.args = args
        self.lines = []
        self.reg_alloc = RegisterAllocator()
        self.loop_count = 0

    # -----------------------------
    # Function prologue / epilogue
    # -----------------------------
    def generate_prologue(self):
        self.lines.append("section .text")
        self.lines.append(f"global {self.func_name}")
        self.lines.append(f"{self.func_name}:")
        self.lines.append("    ; Function prologue")
        self.lines.append("    push rbp")
        self.lines.append("    mov rbp, rsp")
        self.lines.append("    ; Assume float args in rdi, rsi, rdx, rcx, r8, r9")

    def generate_epilogue(self):
        self.lines.append("    ; Function epilogue")
        self.lines.append("    pop rbp")
        self.lines.append("    ret")

    # -----------------------------
    # Node visitors
    # -----------------------------
    def visit_FunctionDef(self, node):
        self.generate_prologue()
        for stmt in node.body:
            self.visit(stmt)
        self.generate_epilogue()

    def visit_Return(self, node):
        self.visit(node.value)
        # Result expected in xmm0

    def visit_BinOp(self, node):
        left = self.evaluate_node(node.left)
        right = self.evaluate_node(node.right)
        op_line = self.binop_to_asm(node.op, left, right)
        self.lines.append(op_line)

    def visit_Name(self, node):
        idx = self.args.index(node.id)
        reg = GENERAL_REGS[idx]
        xmm = self.reg_alloc.allocate_xmm(node.id)
        self.lines.append(f"    movq {xmm}, {reg}    ; Load argument {node.id}")
        return xmm

    def visit_Constant(self, node):
        xmm = self.reg_alloc.allocate_xmm(f"const_{node.value}")
        hexval = float_to_hex(node.value)
        self.lines.append(f"    mov rax, {hexval}    ; Load constant {node.value}")
        self.lines.append(f"    movq {xmm}, rax")
        return xmm

    def binop_to_asm(self, op, left, right):
        if isinstance(op, ast.Add):
            return f"    addsd {left}, {right}    ; add"
        elif isinstance(op, ast.Sub):
            return f"    subsd {left}, {right}    ; sub"
        elif isinstance(op, ast.Mult):
            return f"    mulsd {left}, {right}    ; mul"
        elif isinstance(op, ast.Div):
            return f"    divsd {left}, {right}    ; div"
        else:
            raise NotImplementedError(f"Operator {type(op)} not supported")

    # -----------------------------
    # Loops for array vectorization
    # -----------------------------
    def visit_For(self, node):
        self.loop_count += 1
        loop_id = self.loop_count
        self.lines.append(f"    ; Begin loop {loop_id}")
        # Assume for i in range(n)
        target = node.target.id
        if isinstance(node.iter, ast.Call) and node.iter.func.id == "range":
            range_arg = node.iter.args[0]
            if isinstance(range_arg, ast.Name):
                n_var = range_arg.id
            elif isinstance(range_arg, ast.Constant):
                n_var = range_arg.value
            else:
                n_var = "n"
            self.lines.append(f"    mov rcx, {n_var}    ; loop counter")
            self.lines.append(f"loop_{loop_id}:")
            for stmt in node.body:
                self.visit(stmt)
            self.lines.append(f"    dec rcx")
            self.lines.append(f"    jnz loop_{loop_id}")
        self.lines.append(f"    ; End loop {loop_id}")

    # -----------------------------
    # Evaluate nodes recursively
    # -----------------------------
    def evaluate_node(self, node):
        if isinstance(node, ast.BinOp):
            self.visit_BinOp(node)
            return self.reg_alloc.allocate_xmm("tmp")
        elif isinstance(node, ast.Name):
            return self.visit_Name(node)
        elif isinstance(node, ast.Constant):
            return self.visit_Constant(node)
        else:
            raise NotImplementedError(f"Node {type(node)} not supported")

# -----------------------------
# Main transpile API
# -----------------------------
def transpile_to_asm(func):
    src = inspect.getsource(func)
    tree = ast.parse(src)
    func_node = tree.body[0]
    func_name = func_node.name
    args = [arg.arg for arg in func_node.args.args]

    gen = ASMGenerator(func_name, args)
    gen.visit(func_node)

    asm_file = Path(f"./{func_name}.asm")
    with open(asm_file, "w") as f:
        f.write("\n".join(gen.lines))

    print(f"[piler] Generated assembly for {func_name} -> {asm_file}")
    return asm_file