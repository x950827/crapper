"""Kotlin functions and cyclomatic complexity, counted like the Java reader.

Decisions are `if`, `for`, `while`, `do`, `catch`, `?:`, each `when` entry
(`else` included, as Java counts `default`), and each `&&` / `||`. Safe calls
(`?.`) and `!!` are not decisions.

Entries are named functions with a body: members of classes, interfaces,
objects, companion objects and enum entries, extension functions, and
top-level functions. Lambdas and local functions stay inside the enclosing
function, as Java lambdas do. Functions in anonymous objects
(`object : Runnable { ... }`) are omitted and do not raise the enclosing
function's complexity, like anonymous classes in Java. Constructors, `init`
blocks and property accessors are not entries.

Names follow the class files kotlinc writes, which is where JaCoCo reports
them. Top-level functions belong to the file facade class (`Billing.kt` ->
`BillingKt`, `my-utils.kt` -> `My_utilsKt`, or the name in `@file:JvmName`);
with `@file:JvmMultifileClass` the bodies live in `Facade__FileKt`. Nested
types use `.` in the namespace and `$` in the JaCoCo name; an unnamed
companion object is `Companion`. Backticks are dropped from names.
"""

import re
from pathlib import Path

from crapper.languages.treesitter import (
    child_of_type,
    complexity,
    descendants,
    end_line,
    node_text,
    parse,
    qualify,
    start_line,
)
from crapper.model import Function

_TYPES = {"class_declaration", "object_declaration", "companion_object", "enum_entry"}
_DECISIONS = {
    "if_expression",
    "for_statement",
    "while_statement",
    "do_while_statement",
    "catch_block",
    "elvis_expression",
    "when_entry",
    "conjunction_expression",
    "disjunction_expression",
}
# A function under one of these is local to it, never an entry of its own.
_OPAQUE = {
    "lambda_literal",
    "anonymous_function",
    "getter",
    "setter",
    "anonymous_initializer",
    "secondary_constructor",
    "object_literal",
}


def _is_decision(node) -> bool:
    return node.type in _DECISIONS


def _skip(node) -> bool:
    return node.type in _TYPES or node.type in {"object_literal", "class_body"}


def _unquote(text: str) -> str:
    return text.replace("`", "")


def _type_name(data: bytes, node) -> str:
    ident = child_of_type(node, "type_identifier", "simple_identifier")
    if ident is None:
        return "Companion"
    return _unquote(node_text(data, ident))


def _package(data: bytes, root) -> str | None:
    header = child_of_type(root, "package_header")
    ident = child_of_type(header, "identifier") if header is not None else None
    return _unquote(node_text(data, ident)) if ident is not None else None


def _annotation(data: bytes, node) -> tuple[str, str | None] | None:
    """Simple name and first string argument of one `@file:` annotation."""

    if node.type == "user_type":
        return _simple_name(data, node), None
    user = child_of_type(node, "user_type")
    if node.type != "constructor_invocation" or user is None:
        return None
    strings = (child for child in descendants(node) if child.type == "string_content")
    content = next(strings, None)
    return _simple_name(data, user), node_text(data, content) if content is not None else None


def _simple_name(data: bytes, user_type) -> str:
    return node_text(data, user_type).rsplit(".", 1)[-1].strip()


def _file_annotations(data: bytes, root) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for annotation in root.children:
        if annotation.type != "file_annotation":
            continue
        for child in annotation.children:
            entry = _annotation(data, child)
            if entry is not None:
                found.setdefault(*entry)
    return found


def _file_class(path: str) -> str:
    """The facade kotlinc names after the file: invalid characters become `_`."""

    name = re.sub(r"\W", "_", Path(path).stem)
    if not (name[:1].isalpha() or name[:1] == "_"):
        name = "_" + name
    if name[:1].isascii():
        name = name[:1].upper() + name[1:]
    return name + "Kt"


def _facade(data: bytes, root, path: str) -> tuple[str, str]:
    """Namespace class and JaCoCo class of the file's top-level functions."""

    file_class = _file_class(path)
    annotations = _file_annotations(data, root)
    facade = annotations.get("JvmName") or file_class
    if "JvmMultifileClass" in annotations:
        return facade, f"{facade}__{file_class}"
    return facade, facade


def _owner(package: str | None, names: list[str], facade: tuple[str, str]) -> tuple[str, str]:
    if names:
        return qualify(package, names, "."), qualify(package, names, "$")
    return qualify(package, [facade[0]], "."), qualify(package, [facade[1]], "$")


def _function(data: bytes, node, path: str, owner: tuple[str, str]) -> Function | None:
    ident = child_of_type(node, "simple_identifier")
    if ident is None or child_of_type(node, "function_body") is None:
        return None
    namespace, jacoco_class = owner
    return Function(
        name=_unquote(node_text(data, ident)),
        namespace=namespace,
        complexity=complexity(node, _is_decision, _skip),
        start_line=start_line(node),
        end_line=end_line(node),
        path=path,
        language="kotlin",
        jacoco_class=jacoco_class,
    )


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    del project_root
    data, tree = parse(source, "kotlin")
    root = tree.root_node
    package = _package(data, root)
    facade = _facade(data, root, path)
    found: list[Function] = []
    stack: list[tuple[object, list[str]]] = [(root, [])]
    while stack:
        node, names = stack.pop()
        if node.type == "function_declaration":
            function = _function(data, node, path, _owner(package, names, facade))
            if function is not None:
                found.append(function)
            continue
        if node.type in _OPAQUE:
            continue
        if node.type in _TYPES:
            names = [*names, _type_name(data, node)]
        stack.extend((child, names) for child in reversed(node.children))
    return found
