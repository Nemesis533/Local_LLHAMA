import ast
import os

def parse_docstring(docstring):
    lines = docstring.strip().split('\n')
    description = []
    params = []
    for line in lines:
        line = line.strip()
        if line.startswith('@brief'):
            description.append(line.replace('@brief', '').strip())
        elif line.startswith('@param'):
            param_line = line.replace('@param', '').strip()
            # split param_name and description safely
            if ' ' in param_line:
                param_name, param_desc = param_line.split(' ', 1)
            else:
                param_name, param_desc = param_line, ''
            params.append((param_name.strip(), param_desc.strip()))
    return description, params

def process_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            tree = ast.parse(f.read(), filename=file_path)
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
            return ""
    
    md_output = f"# Documentation for `{os.path.basename(file_path)}`\n\n"
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            docstring = ast.get_docstring(node)
            if docstring:
                description, params = parse_docstring(docstring)
                md_output += f"## Function `{node.name}`\n\n"
                if description:
                    md_output += "**Description:**\n\n" + " ".join(description) + "\n\n"
                if params:
                    md_output += "**Parameters:**\n\n"
                    for name, desc in params:
                        md_output += f"- `{name}`: {desc}\n"
                md_output += "\n"
    return md_output

def process_folder(folder_path, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                print(f"Processing {file_path} ...")
                md = process_file(file_path)
                if md.strip():
                    # save markdown with same relative path, but flatten or keep structure if you want
                    relative_path = os.path.relpath(file_path, folder_path)
                    md_file_name = os.path.splitext(relative_path)[0].replace(os.sep, '_') + ".md"
                    output_path = os.path.join(output_folder, md_file_name)
                    with open(output_path, 'w', encoding='utf-8') as md_file:
                        md_file.write(md)

if __name__ == "__main__":
    # Set your source folder and wiki output folder here:
    source_folder = "./local_llhama"   # or path to your project folder
    wiki_output_folder = "./wiki_docs"
    process_folder(source_folder, wiki_output_folder)
    print("Done! Markdown docs are in:", wiki_output_folder)
