import os
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_java
import tree_sitter_python
import tree_sitter_go

REPOS_DIR = "/tmp/Repos"

# Define Parsers
PARSERS = {
    ".java": Parser(Language(tree_sitter_java.language())),
    ".py": Parser(Language(tree_sitter_python.language())),
    ".go": Parser(Language(tree_sitter_go.language())),
}


def get_package_or_module(root, ext):
    """Dosya türüne göre package veya module adını bulur."""
    if ext == ".java":
        for child in root.children:
            if child.type == "package_declaration":
                return (
                    child.text.decode()
                    .replace("package", "")
                    .replace(";", "")
                    .strip()
                )
    elif ext == ".go":
        for child in root.children:
            if child.type == "package_clause":
                return (
                    child.text.decode()
                    .replace("package", "")
                    .strip()
                )
    return None


def visit(node, file_ext, current_context={"class": None, "package": None}):
    """Ağaç yapısını gezer ve bulduğu metot/fonksiyon verilerini yield eder."""
    
    # ------------------ JAVA İÇİN LOGIC ------------------
    if file_ext == ".java":
        if node.type == "class_declaration":
            class_name = node.child_by_field_name("name").text.decode()
            current_context["class"] = class_name

        elif node.type == "method_declaration":
            method_name = node.child_by_field_name("name").text.decode()
            yield extract_node_data(node, method_name, "method", current_context)

    # ------------------ PYTHON İÇİN LOGIC ------------------
    elif file_ext == ".py":
        if node.type == "class_definition":
            class_name = node.child_by_field_name("name").text.decode()
            current_context["class"] = class_name
            #if not current_context.get('class'):
                #current_context['class'] == Path(file_path).stem

        elif node.type == "function_definition":
            func_name = node.child_by_field_name("name").text.decode()
            node_type = "method" if current_context["class"] else "function"
            class_name = func_name # yeni ekledim
            current_context["class"] = class_name # yeni ekledim
            yield extract_node_data(node, func_name, node_type, current_context)

    # ------------------ GO İÇİN LOGIC ------------------
    elif file_ext == ".go":
        if node.type == "function_declaration":
            func_name = node.child_by_field_name("name").text.decode()
            class_name = func_name # yeni ekledim 
            current_context['class'] = class_name # yeni ekledim
            yield extract_node_data(node, func_name, "function", current_context)
        elif node.type == "method_declaration":
            method_name = node.child_by_field_name("name").text.decode()
            class_name = method_name # yeni ekledim 
            current_context['class'] = class_name # yeni ekledim 
            yield extract_node_data(node, method_name, "method", current_context)

    # Rekürsif olarak alt nodeları gez ve onlardan gelen verileri de yield et
    for child in node.children:
        yield from visit(child, file_ext, current_context.copy())


def extract_node_data(node, name, node_type, context):
    """Bulunan kod bloğundan embedding_text ve metadata sözlüğünü hazırlar."""
    code = node.text.decode()

    comment = ""
    prev = node.prev_named_sibling
    if prev and prev.type in ["block_comment", "comment", "expression_statement"]:
        comment = prev.text.decode().strip()

    embedding_text = f"{comment}\n\n{code}" if comment else code

    metadata = {
        "project": context.get("project_name"),
        "language": context.get("language"),
        "package_or_module": context.get("package"),
        "class": context.get("class"),
        "type": node_type,
        "name": name,
        "start_line": node.start_point.row + 1,
        "end_line": node.end_point.row + 1,
        "file_path": context.get("file_path")
    }

    # Diğer dosyada kullanabilmek için temiz bir sözlük yapısı dönüyoruz
    return {
        "embedding_text": embedding_text,
        "code": code,
        "comment": comment,
        "metadata": metadata
    }


def parse_all_repositories(root_path):
    """
    Belirtilen ana dizindeki tüm repoları tarar ve her bulduğu 
    fonksiyon/metot için veri üreten bir generator döner.
    """
    for root_dir, dirs, files in os.walk(root_path):
        for file in files:
            ext = os.path.splitext(file)[1]

            if ext in PARSERS:
                file_path = os.path.join(root_dir, file)
                relative_path = os.path.relpath(file_path, root_path)
                project_name = relative_path.split(os.sep)[0]

                lang_map = {".java": "Java", ".py": "Python", ".go": "Go"}

                with open(file_path, "rb") as f:
                    source = f.read()

                parser = PARSERS[ext]
                tree = parser.parse(source)
                root_node = tree.root_node

                package_name = get_package_or_module(root_node, ext)
                if not package_name:
                    package_name = os.path.dirname(relative_path).replace(os.sep, ".")

                initial_context = {
                    "project_name": project_name,
                    "language": lang_map[ext],
                    "package": package_name,
                    "class": None,
                    "file_path": relative_path,
                }

                # visit generator olduğu için yield from ile dışarı aktarıyoruz
                yield from visit(root_node, ext, initial_context)
