import ast

def get_defined_funcs(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}

def get_called_funcs_in_func(filename, target_func_name):
    with open(filename, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())
    
    called_funcs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == target_func_name:
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    called_funcs.add(child.func.id)
    return called_funcs

defined = get_defined_funcs('app.py')
called = get_called_funcs_in_func('app.py', 'create_tables_and_admin_user')

missing = [func for func in called if func not in defined and func.startswith('_')]
print("Missing functions:", missing)
