"""Static parameter-contract checks for pytest-discoverable ``check_*`` functions."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Iterable


PYTEST_BUILTIN_FIXTURES = frozenset(
    {
        "cache",
        "capfd",
        "capfdbinary",
        "caplog",
        "capsys",
        "capsysbinary",
        "doctest_namespace",
        "event_loop",
        "event_loop_policy",
        "monkeypatch",
        "pytestconfig",
        "record_property",
        "record_testsuite_property",
        "record_xml_attribute",
        "recwarn",
        "request",
        "tmp_path",
        "tmp_path_factory",
        "tmpdir",
        "tmpdir_factory",
        "unused_tcp_port",
        "unused_tcp_port_factory",
        "unused_udp_port",
        "unused_udp_port_factory",
    }
)


class ParameterContractError(ValueError):
    """Raised when a discoverable check cannot be called safely by pytest."""


def collected_function_identity(
    module_key: str,
    original_name: object,
    *,
    module_level: bool,
    skipped: bool,
) -> tuple[str, str] | None:
    """Return a strict pytest function identity without parsing a display node id."""

    if (
        skipped
        or not module_level
        or not isinstance(original_name, str)
        or not original_name.isidentifier()
    ):
        return None
    return module_key, original_name


@dataclass(frozen=True)
class CheckParameterContract:
    name: str
    required: tuple[str, ...]
    positional_only: tuple[str, ...]
    fixture_parameters: tuple[str, ...]
    parametrized_parameters: tuple[str, ...]
    unsatisfied: tuple[str, ...]

    @property
    def category(self) -> str:
        if self.unsatisfied:
            return "unsatisfied"
        if not self.required:
            return "zero_parameter"
        return "fixture_or_parametrize"


def _required_parameter_groups(
    node: ast.AsyncFunctionDef | ast.FunctionDef,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    positional = [*node.args.posonlyargs, *node.args.args]
    required_positional = positional[: len(positional) - len(node.args.defaults)]
    required_positional_only = required_positional[: len(node.args.posonlyargs)]
    required_keyword_only = [
        arg
        for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults)
        if default is None
    ]
    required = tuple(arg.arg for arg in [*required_positional, *required_keyword_only])
    positional_only = tuple(arg.arg for arg in required_positional_only)
    return required, positional_only


def _required_parameters(node: ast.AsyncFunctionDef | ast.FunctionDef) -> tuple[str, ...]:
    required, _ = _required_parameter_groups(node)
    return required


def _bound_target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Starred):
        return _bound_target_names(target.value)
    if isinstance(target, (ast.List, ast.Tuple)):
        return {
            name
            for item in target.elts
            for name in _bound_target_names(item)
        }
    return set()


class _ModuleExecutionBindings(ast.NodeVisitor):
    """Collect module-scope bindings without entering nested lexical scopes."""

    def __init__(self, ignored_imports: dict[int, set[str]]) -> None:
        self.names: set[str] = set()
        self._ignored_imports = ignored_imports

    def _bind(self, target: ast.AST) -> None:
        self.names.update(_bound_target_names(target))

    def visit_Import(self, node: ast.Import) -> None:
        ignored = self._ignored_imports.get(id(node), set())
        self.names.update(
            local_name
            for alias in node.names
            if (local_name := alias.asname or alias.name.split(".", 1)[0]) not in ignored
        )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        ignored = self._ignored_imports.get(id(node), set())
        self.names.update(
            local_name
            for alias in node.names
            if alias.name != "*"
            and (local_name := alias.asname or alias.name) not in ignored
        )

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._bind(target)
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._bind(node.target)
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._bind(node.target)
        self.visit(node.value)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._bind(node.target)
        self.visit(node.value)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self._bind(target)

    def visit_For(self, node: ast.For | ast.AsyncFor) -> None:
        self._bind(node.target)
        self.visit(node.iter)
        for statement in [*node.body, *node.orelse]:
            self.visit(statement)

    visit_AsyncFor = visit_For

    def visit_With(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind(item.optional_vars)
        for statement in node.body:
            self.visit(statement)

    visit_AsyncWith = visit_With

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self.names.add(node.name)
        for statement in node.body:
            self.visit(statement)

    def _visit_definition_expressions(
        self,
        node: ast.AsyncFunctionDef | ast.FunctionDef,
    ) -> None:
        self.names.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        for argument in [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]:
            if argument.annotation is not None:
                self.visit(argument.annotation)
        for argument in (node.args.vararg, node.args.kwarg):
            if argument is not None and argument.annotation is not None:
                self.visit(argument.annotation)
        if node.returns is not None:
            self.visit(node.returns)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_definition_expressions(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_definition_expressions(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)
        for expression in [*node.decorator_list, *node.bases]:
            self.visit(expression)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_ListComp(self, node: ast.ListComp) -> None:
        return

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.pattern is not None:
            self.visit(node.pattern)
        if node.name:
            self.names.add(node.name)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self.names.add(node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        for key in node.keys:
            self.visit(key)
        for pattern in node.patterns:
            self.visit(pattern)
        if node.rest:
            self.names.add(node.rest)


def _pytest_import_aliases(
    tree: ast.Module,
) -> tuple[set[str], set[str], set[str]]:
    module_aliases: set[str] = set()
    fixture_aliases: set[str] = set()
    mark_aliases: set[str] = set()
    ignored_imports: dict[int, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pytest":
                    local_name = alias.asname or alias.name
                    module_aliases.add(local_name)
                    ignored_imports.setdefault(id(node), set()).add(local_name)
        elif isinstance(node, ast.ImportFrom) and node.module == "pytest":
            for alias in node.names:
                local_name = alias.asname or alias.name
                if alias.name == "fixture":
                    fixture_aliases.add(local_name)
                    ignored_imports.setdefault(id(node), set()).add(local_name)
                elif alias.name == "mark":
                    mark_aliases.add(local_name)
                    ignored_imports.setdefault(id(node), set()).add(local_name)
    collector = _ModuleExecutionBindings(ignored_imports)
    collector.visit(tree)
    rebound = collector.names
    ambiguous = (
        (module_aliases & fixture_aliases)
        | (module_aliases & mark_aliases)
        | (fixture_aliases & mark_aliases)
    )
    rebound.update(ambiguous)
    module_aliases.difference_update(rebound)
    fixture_aliases.difference_update(rebound)
    mark_aliases.difference_update(rebound)
    return module_aliases, fixture_aliases, mark_aliases


def _literal_parametrize_names(value: ast.expr, *, function_name: str) -> set[str]:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return {item.strip() for item in value.value.split(",") if item.strip()}
    if isinstance(value, (ast.List, ast.Tuple)):
        names: set[str] = set()
        for item in value.elts:
            if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                raise ParameterContractError(
                    f"{function_name}: parametrize argnames must be literal strings"
                )
            names.add(item.value)
        return names
    raise ParameterContractError(
        f"{function_name}: parametrize argnames must be a literal string/list/tuple"
    )


def _is_parametrize_decorator(
    decorator: ast.Call,
    *,
    pytest_aliases: set[str],
    mark_aliases: set[str],
) -> bool:
    function = decorator.func
    if not isinstance(function, ast.Attribute) or function.attr != "parametrize":
        return False
    owner = function.value
    if isinstance(owner, ast.Name):
        return owner.id in mark_aliases
    return (
        isinstance(owner, ast.Attribute)
        and owner.attr == "mark"
        and isinstance(owner.value, ast.Name)
        and owner.value.id in pytest_aliases
    )


def _parametrized_parameters(
    node: ast.AsyncFunctionDef | ast.FunctionDef,
    *,
    pytest_aliases: set[str],
    mark_aliases: set[str],
) -> set[str]:
    names: set[str] = set()
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call) or not _is_parametrize_decorator(
            decorator,
            pytest_aliases=pytest_aliases,
            mark_aliases=mark_aliases,
        ):
            continue
        argnames = decorator.args[0] if decorator.args else None
        if argnames is None:
            argnames = next(
                (keyword.value for keyword in decorator.keywords if keyword.arg == "argnames"),
                None,
            )
        if argnames is None:
            raise ParameterContractError(f"{node.name}: parametrize is missing argnames")
        names.update(_literal_parametrize_names(argnames, function_name=node.name))
    return names


def fixture_names_from_source(source: str, *, filename: str) -> set[str]:
    tree = ast.parse(source, filename=filename)
    pytest_aliases, fixture_aliases, _ = _pytest_import_aliases(tree)
    fixtures: set[str] = set(PYTEST_BUILTIN_FIXTURES)
    locally_declared: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for decorator in node.decorator_list:
            fixture_call = decorator if isinstance(decorator, ast.Call) else None
            fixture_decorator = fixture_call.func if fixture_call else decorator
            is_direct_fixture = (
                isinstance(fixture_decorator, ast.Name)
                and fixture_decorator.id in fixture_aliases
            )
            is_module_fixture = (
                isinstance(fixture_decorator, ast.Attribute)
                and fixture_decorator.attr == "fixture"
                and isinstance(fixture_decorator.value, ast.Name)
                and fixture_decorator.value.id in pytest_aliases
            )
            if not is_direct_fixture and not is_module_fixture:
                continue
            fixture_name = node.name
            if fixture_call:
                if fixture_call.args:
                    raise ParameterContractError(
                        f"{filename}:{node.name}: fixture decorator positional "
                        "arguments are not statically supported"
                    )
                explicit_names = [
                    keyword.value
                    for keyword in fixture_call.keywords
                    if keyword.arg == "name"
                ]
                if len(explicit_names) > 1:
                    raise ParameterContractError(
                        f"{filename}:{node.name}: fixture name is declared more than once"
                    )
                explicit_name = explicit_names[0] if explicit_names else None
                if explicit_name is not None:
                    if not (
                        isinstance(explicit_name, ast.Constant)
                        and isinstance(explicit_name.value, str)
                        and explicit_name.value
                    ):
                        raise ParameterContractError(
                            f"{filename}:{node.name}: fixture name must be a non-empty "
                            "literal string"
                        )
                    fixture_name = explicit_name.value
            if fixture_name in locally_declared:
                raise ParameterContractError(
                    f"{filename}: duplicate module fixture name {fixture_name}"
                )
            locally_declared.add(fixture_name)
            fixtures.add(fixture_name)
            break
    return fixtures


def analyze_check_parameters(
    source: str,
    *,
    filename: str,
    fixture_names: Iterable[str],
) -> tuple[CheckParameterContract, ...]:
    tree = ast.parse(source, filename=filename)
    pytest_aliases, _, mark_aliases = _pytest_import_aliases(tree)
    available_fixtures = set(fixture_names) | fixture_names_from_source(
        source,
        filename=filename,
    )
    contracts: list[CheckParameterContract] = []
    for node in tree.body:
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if not node.name.startswith("check_"):
            continue
        required, positional_only = _required_parameter_groups(node)
        injectable = set(required) - set(positional_only)
        parametrized = _parametrized_parameters(
            node,
            pytest_aliases=pytest_aliases,
            mark_aliases=mark_aliases,
        )
        fixture_parameters = injectable & available_fixtures
        parametrized_parameters = injectable & parametrized
        unsatisfied = (
            set(positional_only)
            | (injectable - fixture_parameters - parametrized_parameters)
        )
        contracts.append(
            CheckParameterContract(
                name=node.name,
                required=required,
                positional_only=positional_only,
                fixture_parameters=tuple(sorted(fixture_parameters)),
                parametrized_parameters=tuple(sorted(parametrized_parameters)),
                unsatisfied=tuple(sorted(unsatisfied)),
            )
        )
    return tuple(contracts)


def validate_check_parameters(
    source: str,
    *,
    filename: str,
    fixture_names: Iterable[str],
) -> tuple[CheckParameterContract, ...]:
    contracts = analyze_check_parameters(
        source,
        filename=filename,
        fixture_names=fixture_names,
    )
    failures: list[str] = []
    for contract in contracts:
        if not contract.unsatisfied:
            continue
        reasons: list[str] = []
        if contract.positional_only:
            reasons.append(
                "required positional-only parameters cannot be injected by pytest: "
                + ", ".join(contract.positional_only)
            )
        other_unsatisfied = set(contract.unsatisfied) - set(contract.positional_only)
        if other_unsatisfied:
            reasons.append(
                "not fixtures or literal parametrize arguments: "
                + ", ".join(sorted(other_unsatisfied))
            )
        failures.append(f"{filename}::{contract.name} -> {'; '.join(reasons)}")
    if failures:
        raise ParameterContractError(
            "required check parameters are not safely injectable: " + "; ".join(failures)
        )
    return contracts


def required_parameters_for_function(
    source: str,
    *,
    filename: str,
    function_name: str,
) -> tuple[str, ...]:
    tree = ast.parse(source, filename=filename)
    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == function_name:
            return _required_parameters(node)
    raise ParameterContractError(f"{filename}: missing function {function_name}")
