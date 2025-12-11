"""
@file wikidoc_creator.py
@brief A utility script to parse `@brief` and `@param`-style docstrings from Python files
       and generate Markdown documentation.

This tool walks through a folder of Python source files, extracts function-level
documentation, and saves formatted `.md` files for each script.
Automatically cleans the output directory before generating new documentation.
"""

import ast
import os
import shutil


def parse_docstring(docstring):
    """
    @brief Parses a structured docstring to extract brief description and parameter info.

    @param docstring The raw docstring from a Python function.

    @return A tuple (description_lines, params) where:
        - description_lines is a list of brief description lines.
        - params is a list of tuples: (param_name, param_description).
    """
    lines = docstring.strip().split("\n")
    description = []
    params = []
    for line in lines:
        line = line.strip()
        if line.startswith("@brief"):
            description.append(line.replace("@brief", "").strip())
        elif line.startswith("@param"):
            param_line = line.replace("@param", "").strip()
            if " " in param_line:
                param_name, param_desc = param_line.split(" ", 1)
            else:
                param_name, param_desc = param_line, ""
            params.append((param_name.strip(), param_desc.strip()))
    return description, params


def process_file(file_path):
    """
    @brief Parses a Python file and extracts Markdown-formatted documentation
           for all functions with docstrings.

    @param file_path Absolute path to the Python file.

    @return Markdown string containing documentation for all documented functions.
    """
    with open(file_path, "r", encoding="utf-8") as f:
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
    """
    @brief Walks through a folder and generates Markdown docs for each Python file found.
           Clears the output folder before generating new documentation.

    @param folder_path Root folder containing Python source files.
    @param output_folder Directory where the generated Markdown files will be saved.
    """
    # Clean output folder before generating new docs
    if os.path.exists(output_folder):
        print(f"Cleaning existing documentation in {output_folder}...")
        for item in os.listdir(output_folder):
            item_path = os.path.join(output_folder, item)
            # Skip hidden files/folders like .git
            if item.startswith("."):
                continue
            if os.path.isfile(item_path):
                os.remove(item_path)
                print(f"  Removed file: {item}")
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
                print(f"  Removed directory: {item}")
    else:
        os.makedirs(output_folder)
        print(f"Created output folder: {output_folder}")

    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                print(f"Processing {file_path} ...")
                md = process_file(file_path)
                if md.strip():
                    relative_path = os.path.relpath(file_path, folder_path)
                    md_file_name = (
                        os.path.splitext(relative_path)[0].replace(os.sep, "_") + ".md"
                    )
                    output_path = os.path.join(output_folder, md_file_name)
                    with open(output_path, "w", encoding="utf-8") as md_file:
                        md_file.write(md)


if __name__ == "__main__":
    """
    @brief Main execution block. Set the input source directory and output directory for docs here.
    """
    source_folder = "./local_llhama"  # Folder containing your project source code
    wiki_output_folder = "./Local_LLHAMA.wiki"  # Output to wiki folder
    process_folder(source_folder, wiki_output_folder)
    print("Done! Markdown docs are in:", wiki_output_folder)
