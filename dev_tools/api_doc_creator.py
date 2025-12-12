"""
@file api_doc_creator.py
@brief A utility script to generate API documentation from Flask route files.

This tool walks through Flask Blueprint route files, extracts route decorators,
HTTP methods, docstrings, and generates comprehensive API documentation in Markdown.
Automatically cleans the output directory before generating new documentation.
"""

import ast
import os
import shutil


def extract_route_info(node, file_content_lines):
    """
    @brief Extract route information from a function node with route decorators.

    @param node The AST FunctionDef node to analyze.
    @param file_content_lines The full file content as lines for decorator extraction.

    @return Dictionary with route information or None if not a route.
    """
    route_info = {
        "function_name": node.name,
        "routes": [],
        "methods": [],
        "docstring": ast.get_docstring(node) or "No description available.",
        "requires_auth": False,
    }

    # Check decorators
    for decorator in node.decorator_list:
        # Handle simple decorator names
        if isinstance(decorator, ast.Name):
            if decorator.id == "login_required":
                route_info["requires_auth"] = True

        # Handle attribute decorators (blueprint.route)
        elif isinstance(decorator, ast.Attribute):
            if decorator.attr == "route":
                # Try to get the route path from the decorator arguments
                pass

        # Handle Call decorators (the actual route decorators with arguments)
        elif isinstance(decorator, ast.Call):
            # Check if it's a route decorator
            if (
                isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "route"
            ):
                # Extract route path
                if decorator.args:
                    route_arg = decorator.args[0]
                    if isinstance(route_arg, ast.Constant):
                        route_info["routes"].append(route_arg.value)
                    elif isinstance(route_arg, ast.Str):  # Python 3.7 compatibility
                        route_info["routes"].append(route_arg.s)

                # Extract methods from keyword arguments
                for keyword in decorator.keywords:
                    if keyword.arg == "methods":
                        if isinstance(keyword.value, ast.List):
                            for method in keyword.value.elts:
                                if isinstance(method, ast.Constant):
                                    route_info["methods"].append(method.value)
                                elif isinstance(method, ast.Str):
                                    route_info["methods"].append(method.s)

            # Check for login_required
            elif (
                isinstance(decorator.func, ast.Name)
                and decorator.func.id == "login_required"
            ):
                route_info["requires_auth"] = True

    # If no routes found, not a route function
    if not route_info["routes"]:
        return None

    # Default to GET if no methods specified
    if not route_info["methods"]:
        route_info["methods"] = ["GET"]

    return route_info


def parse_docstring_detailed(docstring):
    """
    @brief Parse docstring to extract structured information.

    @param docstring The raw docstring text.

    @return Dictionary with parsed docstring components.
    """
    result = {"brief": "", "description": "", "params": [], "returns": "", "errors": []}

    lines = docstring.strip().split("\n")
    current_section = "description"
    description_lines = []

    for line in lines:
        line = line.strip()

        if line.startswith("@brief"):
            result["brief"] = line.replace("@brief", "").strip()
            current_section = "brief"
        elif line.startswith("@param"):
            param_text = line.replace("@param", "").strip()
            result["params"].append(param_text)
            current_section = "params"
        elif line.startswith("@return"):
            result["returns"] = line.replace("@return", "").strip()
            current_section = "returns"
        elif line.startswith("@error") or line.startswith("@raises"):
            error_text = line.replace("@error", "").replace("@raises", "").strip()
            result["errors"].append(error_text)
            current_section = "errors"
        else:
            if current_section == "description" and line:
                description_lines.append(line)

    result["description"] = (
        " ".join(description_lines) if description_lines else result["brief"]
    )

    return result


def process_route_file(file_path):
    """
    @brief Process a Flask route file and extract API endpoint documentation.

    @param file_path Absolute path to the route Python file.

    @return Markdown string containing API documentation.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError as e:
        print(f"Syntax error in {file_path}: {e}")
        return ""

    # Extract module docstring
    module_doc = ast.get_docstring(tree) or ""

    filename = os.path.basename(file_path)
    md_output = f"# API Documentation: `{filename}`\n\n"

    if module_doc:
        md_output += f"{module_doc}\n\n"

    md_output += "---\n\n"

    # Find all route functions
    routes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            route_info = extract_route_info(node, content.split("\n"))
            if route_info:
                routes.append(route_info)

    if not routes:
        return ""

    # Sort routes by path
    routes.sort(key=lambda x: x["routes"][0] if x["routes"] else "")

    # Generate documentation for each route
    for route in routes:
        for route_path in route["routes"]:
            methods_str = ", ".join(route["methods"])

            md_output += f"## `{methods_str}` {route_path}\n\n"

            # Parse docstring
            doc_parsed = parse_docstring_detailed(route["docstring"])

            # Description
            if doc_parsed["description"]:
                md_output += f"**Description:** {doc_parsed['description']}\n\n"

            # Authentication
            if route["requires_auth"]:
                md_output += "🔒 **Authentication Required:** Yes (login_required)\n\n"

            # Parameters
            if doc_parsed["params"]:
                md_output += "**Parameters:**\n\n"
                for param in doc_parsed["params"]:
                    md_output += f"- {param}\n"
                md_output += "\n"

            # Returns
            if doc_parsed["returns"]:
                md_output += f"**Returns:** {doc_parsed['returns']}\n\n"

            # Errors
            if doc_parsed["errors"]:
                md_output += "**Possible Errors:**\n\n"
                for error in doc_parsed["errors"]:
                    md_output += f"- {error}\n"
                md_output += "\n"

            md_output += "---\n\n"

    return md_output


def process_routes_folder(routes_folder, output_folder):
    """
    @brief Process all route files in a folder and generate API documentation.
           Clears the output folder before generating new documentation.

    @param routes_folder Path to the folder containing Flask route files.
    @param output_folder Directory where the API documentation will be saved.
    """
    # Clean output folder before generating new docs
    if os.path.exists(output_folder):
        print(f"Cleaning existing API documentation in {output_folder}...")
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

    # Create an index file
    index_content = "# API Documentation Index\n\n"
    index_content += "This directory contains auto-generated API documentation for all Flask routes.\n\n"
    index_content += "## Available Route Files:\n\n"

    route_files = []

    # Process each route file
    for file in os.listdir(routes_folder):
        if file.endswith(".py") and file != "__init__.py":
            file_path = os.path.join(routes_folder, file)
            print(f"Processing {file_path}...")

            md_content = process_route_file(file_path)

            if md_content.strip():
                md_filename = f"API_{os.path.splitext(file)[0]}.md"
                output_path = os.path.join(output_folder, md_filename)

                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(md_content)

                route_files.append((file, md_filename))
                print(f"  Generated: {md_filename}")

    # Generate index
    for original, doc_file in sorted(route_files):
        index_content += f"- [{original}]({doc_file})\n"

    index_path = os.path.join(output_folder, "API_INDEX.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_content)

    print(f"\nGenerated API documentation index: {index_path}")


if __name__ == "__main__":
    """
    @brief Main execution block.
    """
    routes_folder = "./local_llhama/routes"
    api_docs_folder = "./Local_LLHAMA.wiki/api_docs"

    print("Starting API documentation generation...")
    process_routes_folder(routes_folder, api_docs_folder)
    print(f"\nDone! API documentation is in: {api_docs_folder}")
